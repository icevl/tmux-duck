import { useEffect, useRef } from "react";
import { useTheme } from "@/lib/theme";

// Half-width katakana, digits and a few symbols — the film's glyph mix.
const GLYPHS =
  "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ0123456789:.=*+-<>";
const FONT_PX = 16;
const FRAME_MS = 60;

/**
 * The Matrix theme's digital rain, drawn behind the translucent UI.
 * Off unless the theme is The Matrix and effects are on; never runs for
 * `prefers-reduced-motion`, and pauses while the tab is hidden.
 */
export function MatrixRain() {
  const { preference, effects } = useTheme();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const active =
    preference === "matrix" &&
    effects &&
    !window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!active || !canvas || !ctx) return;

    let drops: number[] = [];
    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.floor(window.innerWidth * dpr);
      canvas.height = Math.floor(window.innerHeight * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const columns = Math.ceil(window.innerWidth / FONT_PX);
      drops = Array.from({ length: columns }, () =>
        Math.floor((Math.random() * window.innerHeight) / FONT_PX),
      );
    };
    resize();
    window.addEventListener("resize", resize);

    let last = 0;
    let frame = 0;
    const draw = (now: number) => {
      frame = requestAnimationFrame(draw);
      if (document.hidden || now - last < FRAME_MS) return;
      last = now;
      // Fade the previous frame instead of clearing: that leaves the trails.
      ctx.fillStyle = "rgba(3, 10, 5, 0.12)";
      ctx.fillRect(0, 0, window.innerWidth, window.innerHeight);
      ctx.font = `${FONT_PX}px "JetBrains Mono", monospace`;
      for (let i = 0; i < drops.length; i++) {
        const glyph = GLYPHS[Math.floor(Math.random() * GLYPHS.length)];
        const y = drops[i] * FONT_PX;
        // The leading glyph is brighter, like the film's.
        ctx.fillStyle = Math.random() < 0.08 ? "#c8ffd0" : "#00ff41";
        ctx.fillText(glyph, i * FONT_PX, y);
        if (y > window.innerHeight && Math.random() > 0.975) drops[i] = 0;
        drops[i]++;
      }
    };
    frame = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    };
  }, [active]);

  if (!active) return null;
  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      // Negative z-index: inside #root, above the page but under every panel.
      className="pointer-events-none fixed inset-0 -z-10 opacity-[0.22]"
    />
  );
}
