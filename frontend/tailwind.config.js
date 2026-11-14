export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {
    colors: { night: "#05070B", paper: "#F4F1EA", heat: "#FF8A3D", cool: "#7CC8FF", stamp: "#C8261E" },
    fontFamily: {
      display: ["Unbounded", "sans-serif"], body: ["Inter", "IBM Plex Sans Arabic", "sans-serif"],
      mono: ["JetBrains Mono", "monospace"], type: ["Special Elite", "monospace"], hand: ["Caveat", "cursive"],
    },
  } },
};
