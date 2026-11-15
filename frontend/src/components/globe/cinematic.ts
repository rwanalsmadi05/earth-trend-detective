import * as THREE from "three";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";

// Cinematic layer for the react-globe.gl globe. Techniques only (day/night terminator, specular ocean, rim light,
// drifting cloud shells, stars, bloom); every texture is NASA imagery served from /textures.
export type QualityLevel = 0 | 1 | 2; // 2 = full, 1 = no bloom / fewer layers / pixel ratio 1, 0 = minimal

export interface Cinematic {
  update(dt: number, reduced: boolean): void;
  setQuality(q: QualityLevel): void;
  quality: QualityLevel;
  material: THREE.ShaderMaterial; // pass to react-globe.gl as the globeMaterial prop
  dispose(): void;
}

const COMMON_VERT = /* glsl */ `
varying vec2 vUv; varying vec3 vWN; varying vec3 vWP;
void main() {
  vUv = uv;
  vWN = normalize(mat3(modelMatrix) * normal);          // world-space normal (the globe mesh is rotated)
  vec4 wp = modelMatrix * vec4(position, 1.0);
  vWP = wp.xyz;
  gl_Position = projectionMatrix * viewMatrix * wp;
}`;

const NOISE = /* glsl */ `
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f*f*(3.0-2.0*f);
  return mix(mix(hash(i), hash(i+vec2(1.0,0.0)), f.x), mix(hash(i+vec2(0.0,1.0)), hash(i+vec2(1.0,1.0)), f.x), f.y); }
float fbm(vec2 p){ float a = 0.5, s = 0.0; for (int i = 0; i < 4; i++) { s += a*noise(p); p *= 2.07; a *= 0.5; } return s; }`;

const GLOBE_FRAG = /* glsl */ `
uniform sampler2D dayMap, nightMap, oceanMap;
uniform vec3 sunDir; uniform float uTime; uniform float uShimmer;
varying vec2 vUv; varying vec3 vWN; varying vec3 vWP;
${NOISE}
void main() {
  vec3 N = normalize(vWN), V = normalize(cameraPosition - vWP), L = normalize(sunDir);
  float ndl = dot(N, L);
  float day = smoothstep(-0.10, 0.30, ndl);                       // soft terminator
  vec3 dayC = texture2D(dayMap, vUv).rgb;
  vec3 nightC = texture2D(nightMap, vUv).rgb;
  float ocean = texture2D(oceanMap, vUv).r;

  // day side: gentle shading toward the terminator
  vec3 col = dayC * (0.30 + 0.80 * smoothstep(-0.05, 0.85, ndl));

  // ocean: animated micro-waves perturb the normal -> shimmer + a sun glint on water only
  vec2 w1 = vUv * vec2(140.0, 70.0) + vec2(uTime * 0.020, uTime * 0.013);
  float n1 = noise(w1) + 0.5 * noise(w1 * 2.3 - uTime * 0.03);
  vec3 Np = normalize(N + vec3(n1 - 0.75, noise(w1 + 17.0) - 0.5, noise(w1 + 41.0) - 0.5) * 0.05 * uShimmer);
  vec3 H = normalize(L + V);
  float nh = max(dot(Np, H), 0.0);
  float glint = (pow(nh, 160.0) * 1.7 + pow(nh, 26.0) * 0.14) * ocean * smoothstep(0.0, 0.35, ndl);
  col += vec3(1.0, 0.92, 0.78) * glint;
  col *= 1.0 + ocean * (n1 - 0.75) * 0.30 * uShimmer * day;

  // night side: faint ambient + NASA city lights
  vec3 lights = pow(nightC, vec3(0.82)) * vec3(1.35, 1.02, 0.66) * 1.7;
  vec3 nightCol = dayC * 0.022 + lights;
  col = mix(nightCol, col, day);

  // rim light, stronger on the sunlit limb
  float fres = pow(1.0 - max(dot(N, V), 0.0), 3.0);
  col += vec3(0.28, 0.55, 1.0) * fres * (0.16 + 0.75 * smoothstep(-0.4, 0.6, ndl));

  gl_FragColor = vec4(col, 1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;

const CLOUD_FRAG = /* glsl */ `
uniform sampler2D cloudMap; uniform vec3 sunDir; uniform float uTime; uniform vec2 uOff; uniform float uOpacity; uniform float uScale;
varying vec2 vUv; varying vec3 vWN; varying vec3 vWP;
${NOISE}
void main() {
  vec3 N = normalize(vWN), L = normalize(sunDir);
  float ndl = dot(N, L);
  float day = smoothstep(-0.14, 0.30, ndl);
  vec2 uv = vec2(vUv.x * uScale + uOff.x, vUv.y * uScale + uOff.y);
  float c = texture2D(cloudMap, uv).r;
  float a = c * uOpacity;
  vec3 col = mix(vec3(0.035, 0.045, 0.075), vec3(1.0, 0.985, 0.95), day);
  gl_FragColor = vec4(col, a);
  #include <colorspace_fragment>
}`;

const STAR_VERT = /* glsl */ `
attribute float aSize; attribute float aPhase; uniform float uTime; uniform float uPx; varying float vA;
void main() {
  float tw = 0.65 + 0.35 * sin(uTime * (0.7 + aPhase) + aPhase * 40.0);
  vA = tw;
  gl_PointSize = aSize * uPx * (0.8 + 0.4 * tw);
  gl_Position = projectionMatrix * viewMatrix * vec4(position, 1.0);
}`;
const STAR_FRAG = /* glsl */ `
varying float vA; uniform vec3 uColor;
void main() {
  float d = length(gl_PointCoord - 0.5);
  float a = smoothstep(0.5, 0.0, d) * vA;
  gl_FragColor = vec4(uColor, a);
  #include <colorspace_fragment>
}`;
const MOTE_VERT = /* glsl */ `
attribute float aPhase; attribute float aSpeed; uniform float uTime; uniform float uPx; varying float vA;
void main() {
  vec3 p = position + vec3(sin(uTime * aSpeed + aPhase * 6.28), cos(uTime * aSpeed * 0.8 + aPhase * 9.0), sin(uTime * aSpeed * 0.6 + aPhase * 3.0)) * 5.0;
  vA = 0.35 + 0.35 * sin(uTime * 0.5 + aPhase * 20.0);
  gl_PointSize = 2.6 * uPx;
  gl_Position = projectionMatrix * viewMatrix * vec4(p, 1.0);
}`;

export function createCinematic(globe: any, opts: { quality: QualityLevel; reduced: boolean }): Cinematic {
  const renderer: THREE.WebGLRenderer = globe.renderer();
  const scene: THREE.Scene = globe.scene();
  const camera: THREE.PerspectiveCamera = globe.camera();
  const composer = globe.postProcessingComposer();
  const R: number = globe.getGlobeRadius();
  const base = (import.meta as any).env?.BASE_URL ?? "/";
  const aniso = Math.min(8, renderer.capabilities.getMaxAnisotropy());

  const loader = new THREE.TextureLoader();
  const tex = (name: string, srgb: boolean) => {
    const t = loader.load(`${base}textures/${name}`);
    t.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
    t.anisotropy = aniso; t.wrapS = THREE.RepeatWrapping; t.wrapT = THREE.MirroredRepeatWrapping; t.generateMipmaps = true; t.minFilter = THREE.LinearMipmapLinearFilter;
    return t;
  };
  const dayMap = tex("day.jpg", true), nightMap = tex("night.jpg", true), oceanMap = tex("ocean.png", false), cloudMap = tex("clouds.jpg", false);

  const sun = new THREE.Vector3(0.6, 0.3, 0.7).normalize();
  const uTime = { value: 0 };
  const uShimmer = { value: 1 };

  // ---- globe surface: day/night + ocean glint + rim ----
  const globeMat = new THREE.ShaderMaterial({
    vertexShader: COMMON_VERT, fragmentShader: GLOBE_FRAG,
    uniforms: { dayMap: { value: dayMap }, nightMap: { value: nightMap }, oceanMap: { value: oceanMap }, sunDir: { value: sun }, uTime, uShimmer },
  });

  // ---- cloud shells at different heights and speeds ----
  const shells = [
    { r: 1.008, speed: 0.0042, off: [0.0, 0.0], opacity: 0.6, scale: 1.0 },
    { r: 1.016, speed: 0.0027, off: [0.37, 0.04], opacity: 0.4, scale: 1.0 },
    { r: 1.026, speed: 0.0016, off: [0.71, -0.03], opacity: 0.28, scale: 1.0 },
  ].map((s) => {
    const mat = new THREE.ShaderMaterial({
      vertexShader: COMMON_VERT, fragmentShader: CLOUD_FRAG, transparent: true, depthWrite: false,
      uniforms: { cloudMap: { value: cloudMap }, sunDir: { value: sun }, uTime, uOff: { value: new THREE.Vector2(s.off[0], s.off[1]) }, uOpacity: { value: s.opacity }, uScale: { value: s.scale } },
    });
    const mesh = new THREE.Mesh(new THREE.SphereGeometry(R * s.r, 72, 72), mat);
    mesh.rotation.y = -Math.PI / 2; // same orientation as the globe mesh
    mesh.renderOrder = 2;
    scene.add(mesh);
    return { mesh, mat, speed: s.speed };
  });

  // ---- background stars + drifting atmosphere motes ----
  const far = Math.min(1800, (camera.far || 4000) * 0.6);
  const rnd = (() => { let s = 1337; return () => ((s = (s * 16807) % 2147483647) - 1) / 2147483646; })();
  const STARS = 1800;
  const sp = new Float32Array(STARS * 3), ss = new Float32Array(STARS), sph = new Float32Array(STARS);
  for (let i = 0; i < STARS; i++) {
    const u = rnd() * 2 - 1, a = rnd() * Math.PI * 2, r = Math.sqrt(1 - u * u);
    sp.set([r * Math.cos(a) * far, u * far, r * Math.sin(a) * far], i * 3);
    ss[i] = 1.0 + Math.pow(rnd(), 3) * 2.6; sph[i] = rnd();
  }
  const starGeo = new THREE.BufferGeometry();
  starGeo.setAttribute("position", new THREE.BufferAttribute(sp, 3)); starGeo.setAttribute("aSize", new THREE.BufferAttribute(ss, 1)); starGeo.setAttribute("aPhase", new THREE.BufferAttribute(sph, 1));
  const px = { value: Math.min(window.devicePixelRatio || 1, 1.5) };
  const starMat = new THREE.ShaderMaterial({ vertexShader: STAR_VERT, fragmentShader: STAR_FRAG, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, uniforms: { uTime, uPx: px, uColor: { value: new THREE.Color(0.8, 0.88, 1.0) } } });
  const stars = new THREE.Points(starGeo, starMat); stars.frustumCulled = false; stars.renderOrder = -1; scene.add(stars);

  const MOTES = 240;
  const mp = new Float32Array(MOTES * 3), mph = new Float32Array(MOTES), msp = new Float32Array(MOTES);
  for (let i = 0; i < MOTES; i++) {
    const u = rnd() * 2 - 1, a = rnd() * Math.PI * 2, r = Math.sqrt(1 - u * u), rad = R * (1.15 + rnd() * 0.8);
    mp.set([r * Math.cos(a) * rad, u * rad, r * Math.sin(a) * rad], i * 3); mph[i] = rnd(); msp[i] = 0.08 + rnd() * 0.18;
  }
  const moteGeo = new THREE.BufferGeometry();
  moteGeo.setAttribute("position", new THREE.BufferAttribute(mp, 3)); moteGeo.setAttribute("aPhase", new THREE.BufferAttribute(mph, 1)); moteGeo.setAttribute("aSpeed", new THREE.BufferAttribute(msp, 1));
  const moteMat = new THREE.ShaderMaterial({ vertexShader: MOTE_VERT, fragmentShader: STAR_FRAG, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, uniforms: { uTime, uPx: px, uColor: { value: new THREE.Color(0.55, 0.75, 1.0) } } });
  const motes = new THREE.Points(moteGeo, moteMat); motes.frustumCulled = false; motes.renderOrder = 3; scene.add(motes);

  // ---- bloom (subtle) + output pass: the composer renders linear, OutputPass converts to sRGB ----
  const size = renderer.getSize(new THREE.Vector2());
  const bloom = new UnrealBloomPass(new THREE.Vector2(size.x, size.y), 0.32, 0.55, 0.86);
  const output = new OutputPass();
  composer.addPass(bloom); composer.addPass(output);
  composer.setSize(size.x, size.y);

  const cam = { dir: new THREE.Vector3(), right: new THREE.Vector3(), up: new THREE.Vector3() };
  let quality: QualityLevel = opts.quality;

  function setQuality(q: QualityLevel) {
    quality = q; api.quality = q;
    bloom.enabled = q >= 2;
    shells[1].mesh.visible = q >= 1; shells[2].mesh.visible = q >= 2;
    motes.visible = q >= 2;
    starGeo.setDrawRange(0, q >= 2 ? STARS : q === 1 ? 900 : 450);
    uShimmer.value = q >= 1 ? 1 : 0;
    const pr = q >= 2 ? Math.min(window.devicePixelRatio || 1, 1.5) : 1;
    renderer.setPixelRatio(pr); composer.setPixelRatio?.(pr); px.value = pr;
    const s = renderer.getSize(new THREE.Vector2()); composer.setSize(s.x, s.y);
  }

  const api: Cinematic = {
    quality,
    material: globeMat,
    setQuality,
    update(dt, reduced) {
      if (!reduced) uTime.value += dt;
      // the sun is fixed relative to the VIEW: the lit side always faces the camera's right, so the terminator and
      // the city lights stay on screen however the user rotates the globe
      cam.dir.copy(camera.position).normalize();
      const e = camera.matrixWorld.elements;
      cam.right.set(e[0], e[1], e[2]).normalize(); cam.up.set(e[4], e[5], e[6]).normalize();
      sun.copy(cam.dir).multiplyScalar(0.5).addScaledVector(cam.right, 0.9).addScaledVector(cam.up, 0.2).normalize();
      if (!reduced) shells.forEach((s) => { s.mesh.rotation.y -= s.speed * dt; });
    },
    dispose() {
      shells.forEach((s) => { scene.remove(s.mesh); s.mesh.geometry.dispose(); s.mat.dispose(); });
      scene.remove(stars); scene.remove(motes); starGeo.dispose(); moteGeo.dispose(); starMat.dispose(); moteMat.dispose();
      composer.removePass?.(bloom); composer.removePass?.(output); bloom.dispose(); output.dispose();
      globeMat.dispose(); [dayMap, nightMap, oceanMap, cloudMap].forEach((t) => t.dispose());
    },
  };
  setQuality(opts.quality);
  const dbg = new URLSearchParams(window.location.search).get("debug") ?? "";
  if (dbg.includes("noclouds")) shells.forEach((x) => (x.mesh.visible = false));
  if (dbg.includes("nostars")) { stars.visible = false; motes.visible = false; }
  return api;
}
