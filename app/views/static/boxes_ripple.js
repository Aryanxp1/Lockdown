/**
 * Lockdown — Interactive Background Boxes Ripple Effect
 * Inspired by Aceternity UI Background Boxes & Ripple Effect.
 * Zero-dependency HTML5 Canvas rendering an interactive grid of boxes
 * with cursor-hover illumination and radial expanding click ripple waves.
 */

(function () {
  function initBoxesRipple() {
    const canvas = document.getElementById("boxes-ripple-canvas");
    if (!canvas) return;

    const hero = canvas.closest(".editorial-hero") || canvas.parentElement;
    if (!hero) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let width = 0;
    let height = 0;
    let dpr = window.devicePixelRatio || 1;

    // Grid configuration
    const BOX_SIZE = 54;
    let cols = 0;
    let rows = 0;
    let boxes = []; // 2D array [row][col]

    // Color palette for boxes (Black, White, Grey with Crimson Red from screenshot)
    const PALETTE = [
      { r: 239, g: 68, b: 68 },   // Crimson Red
      { r: 248, g: 113, b: 113 }, // Bright Coral Red
      { r: 255, g: 255, b: 255 }, // Stark White
      { r: 185, g: 28, b: 28 },   // Deep Red
      { r: 212, g: 212, b: 216 }, // Silver Grey
      { r: 113, g: 113, b: 122 }, // Zinc Grey
    ];

    function resize() {
      const rect = hero.getBoundingClientRect();
      width = Math.ceil(rect.width) || 1200;
      height = Math.ceil(rect.height) || 600;

      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.resetTransform ? ctx.resetTransform() : ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.scale(dpr, dpr);

      cols = Math.ceil(width / BOX_SIZE) + 1;
      rows = Math.ceil(height / BOX_SIZE) + 1;

      // Rebuild or preserve boxes
      const newBoxes = [];
      for (let r = 0; r < rows; r++) {
        const rowArr = [];
        for (let c = 0; c < cols; c++) {
          const oldBox = (boxes[r] && boxes[r][c]) ? boxes[r][c] : null;
          rowArr.push({
            c,
            r,
            x: c * BOX_SIZE,
            y: r * BOX_SIZE,
            highlight: oldBox ? oldBox.highlight : 0,
            color: oldBox ? oldBox.color : PALETTE[Math.floor(Math.random() * PALETTE.length)],
          });
        }
        newBoxes.push(rowArr);
      }
      boxes = newBoxes;
    }

    resize();
    window.addEventListener("resize", resize);

    // Active ripples queue
    const ripples = [];

    function triggerRipple(originX, originY) {
      ripples.push({
        x: originX,
        y: originY,
        startTime: performance.now(),
        speed: 0.42, // pixels per millisecond
        maxDist: Math.hypot(width, height) * 1.1,
        colorIndex: Math.floor(Math.random() * PALETTE.length),
      });
      // Cap ripples array
      if (ripples.length > 8) ripples.shift();
    }

    // Hover interaction
    let lastHoverCol = -1;
    let lastHoverRow = -1;

    function handlePointerMove(clientX, clientY) {
      const rect = hero.getBoundingClientRect();
      const x = clientX - rect.left;
      const y = clientY - rect.top;

      if (x < 0 || x > width || y < 0 || y > height) return;

      const c = Math.floor(x / BOX_SIZE);
      const r = Math.floor(y / BOX_SIZE);

      if (c >= 0 && c < cols && r >= 0 && r < rows) {
        if (c !== lastHoverCol || r !== lastHoverRow) {
          lastHoverCol = c;
          lastHoverRow = r;

          // Light up hovered box and neighbors
          for (let dr = -1; dr <= 1; dr++) {
            for (let dc = -1; dc <= 1; dc++) {
              const nr = r + dr;
              const nc = c + dc;
              if (nr >= 0 && nr < rows && nc >= 0 && nc < cols) {
                const b = boxes[nr][nc];
                const intensity = (dr === 0 && dc === 0) ? 0.95 : 0.45;
                if (b.highlight < intensity) {
                  b.highlight = intensity;
                  b.color = PALETTE[Math.floor(Math.random() * PALETTE.length)];
                }
              }
            }
          }
        }
      }
    }

    hero.addEventListener("mousemove", e => {
      handlePointerMove(e.clientX, e.clientY);
    });

    hero.addEventListener("click", e => {
      // Don't intercept clicks on links or buttons
      if (e.target.closest("a, button, input, select, textarea")) return;
      const rect = hero.getBoundingClientRect();
      triggerRipple(e.clientX - rect.left, e.clientY - rect.top);
    });

    hero.addEventListener("touchstart", e => {
      if (e.touches.length > 0) {
        const t = e.touches[0];
        if (e.target.closest("a, button, input, select, textarea")) return;
        const rect = hero.getBoundingClientRect();
        triggerRipple(t.clientX - rect.left, t.clientY - rect.top);
      }
    }, { passive: true });

    // Initial gentle demonstration ripple after 800ms
    setTimeout(() => {
      triggerRipple(width * 0.35, height * 0.4);
    }, 800);

    // Animation render loop
    let lastTime = performance.now();

    function render(now) {
      const dt = Math.min(now - lastTime, 100);
      lastTime = now;

      ctx.clearRect(0, 0, width, height);

      // 1. Process active ripples
      for (let i = ripples.length - 1; i >= 0; i--) {
        const rip = ripples[i];
        const elapsed = now - rip.startTime;
        const currentRadius = elapsed * rip.speed;

        if (currentRadius > rip.maxDist) {
          ripples.splice(i, 1);
          continue;
        }

        const ringWidth = BOX_SIZE * 1.5;

        // Check which boxes intersect the wave ring
        for (let r = 0; r < rows; r++) {
          for (let c = 0; c < cols; c++) {
            const b = boxes[r][c];
            const boxCenterX = b.x + BOX_SIZE / 2;
            const boxCenterY = b.y + BOX_SIZE / 2;
            const dist = Math.hypot(boxCenterX - rip.x, boxCenterY - rip.y);

            const distFromWave = Math.abs(dist - currentRadius);
            if (distFromWave < ringWidth) {
              const wavePower = (1 - distFromWave / ringWidth);
              const attenuation = Math.max(0, 1 - (currentRadius / rip.maxDist));
              const impact = wavePower * attenuation * 0.9;

              if (impact > b.highlight) {
                b.highlight = impact;
                b.color = PALETTE[rip.colorIndex % PALETTE.length];
              }
            }
          }
        }
      }

      // 2. Render Grid Boxes
      const baseBorder = "rgba(255, 255, 255, 0.05)";
      ctx.lineWidth = 1;

      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const b = boxes[r][c];

          // Decay highlight
          if (b.highlight > 0.005) {
            b.highlight -= 0.016 * (dt / 16.6);
            if (b.highlight < 0) b.highlight = 0;
          }

          // Draw box border
          if (b.highlight > 0.02) {
            const rgb = b.color;
            ctx.fillStyle = `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${b.highlight * 0.16})`;
            ctx.fillRect(b.x, b.y, BOX_SIZE, BOX_SIZE);

            ctx.strokeStyle = `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${Math.min(1, b.highlight * 0.75 + 0.05)})`;
            ctx.strokeRect(b.x + 0.5, b.y + 0.5, BOX_SIZE - 1, BOX_SIZE - 1);
          } else {
            ctx.strokeStyle = baseBorder;
            ctx.strokeRect(b.x + 0.5, b.y + 0.5, BOX_SIZE - 1, BOX_SIZE - 1);
          }
        }
      }

      // 3. Draw intersection crosses '+' at grid vertices
      ctx.fillStyle = "rgba(255, 255, 255, 0.12)";
      for (let r = 0; r <= rows; r++) {
        for (let c = 0; c <= cols; c++) {
          const vx = c * BOX_SIZE;
          const vy = r * BOX_SIZE;

          // Check if nearby box is glowing
          let glow = 0;
          if (r < rows && c < cols && boxes[r][c].highlight > 0.1) glow = Math.max(glow, boxes[r][c].highlight);
          if (r > 0 && c < cols && boxes[r - 1][c].highlight > 0.1) glow = Math.max(glow, boxes[r - 1][c].highlight);

          if (glow > 0.1) {
            ctx.fillStyle = `rgba(239, 68, 68, ${glow * 0.8})`;
            ctx.fillRect(vx - 2, vy, 5, 1);
            ctx.fillRect(vx, vy - 2, 1, 5);
          } else {
            ctx.fillStyle = "rgba(255, 255, 255, 0.08)";
            ctx.fillRect(vx - 2, vy, 5, 1);
            ctx.fillRect(vx, vy - 2, 1, 5);
          }
        }
      }

      // 4. Subtle Radial Vignette Fade (Aceternity Hero look)
      const vignette = ctx.createRadialGradient(
        width * 0.5, height * 0.45, Math.min(width, height) * 0.25,
        width * 0.5, height * 0.45, Math.max(width, height) * 0.75
      );
      vignette.addColorStop(0, "rgba(5, 5, 8, 0)");
      vignette.addColorStop(0.7, "rgba(5, 5, 8, 0.35)");
      vignette.addColorStop(1, "rgba(5, 5, 8, 0.88)");

      ctx.fillStyle = vignette;
      ctx.fillRect(0, 0, width, height);

      requestAnimationFrame(render);
    }

    requestAnimationFrame(render);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initBoxesRipple);
  } else {
    initBoxesRipple();
  }
})();
