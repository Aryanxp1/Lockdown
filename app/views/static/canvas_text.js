/**
 * Lockdown — Interactive Canvas Text Matrix
 * Inspired by Aceternity UI Canvas Text component (https://ui.aceternity.com/components/canvas-text).
 * Generates an interactive particle matrix and energy web around the main headline,
 * reacting to mouse proximity with fluid particle dispersion, spring return, and radiant red/white sparks.
 */

(function () {
  function initCanvasText() {
    const canvas = document.getElementById("hero-canvas-text");
    if (!canvas) return;

    const wrap = canvas.closest(".hero-statement-wrap") || canvas.parentElement;
    if (!wrap) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let width = 0;
    let height = 0;
    let dpr = window.devicePixelRatio || 1;

    let particles = [];
    const PARTICLE_SPACING = 20;

    // Mouse tracking
    let mouse = { x: -9999, y: -9999, radius: 95, active: false };

    function resize() {
      const rect = wrap.getBoundingClientRect();
      width = Math.ceil(rect.width) || 480;
      height = Math.ceil(rect.height) || 280;

      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.resetTransform ? ctx.resetTransform() : ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.scale(dpr, dpr);

      buildParticles();
    }

    function buildParticles() {
      particles = [];
      const cols = Math.floor(width / PARTICLE_SPACING);
      const rows = Math.floor(height / PARTICLE_SPACING);

      for (let r = 0; r <= rows; r++) {
        for (let c = 0; c <= cols; c++) {
          const originX = c * PARTICLE_SPACING + (r % 2 === 0 ? 0 : PARTICLE_SPACING * 0.5);
          const originY = r * PARTICLE_SPACING;

          // Only keep particles within bounds and with slight density variations
          if (originX > width || originY > height) continue;

          // Assign color role: 50% silver, 35% crimson red, 15% bright white
          const rand = Math.random();
          let colorType = "silver";
          if (rand < 0.35) colorType = "red";
          else if (rand < 0.50) colorType = "white";

          particles.push({
            originX,
            originY,
            x: originX,
            y: originY,
            vx: 0,
            vy: 0,
            radius: Math.random() * 1.4 + 0.8,
            colorType,
            baseAlpha: Math.random() * 0.25 + 0.12,
            alpha: 0.15,
            spark: 0,
            seed: Math.random() * 100,
          });
        }
      }
    }

    resize();
    window.addEventListener("resize", resize);

    wrap.addEventListener("mousemove", e => {
      const rect = wrap.getBoundingClientRect();
      mouse.x = e.clientX - rect.left;
      mouse.y = e.clientY - rect.top;
      mouse.active = true;
    });

    wrap.addEventListener("mouseleave", () => {
      mouse.active = false;
      mouse.x = -9999;
      mouse.y = -9999;
    });

    wrap.addEventListener("touchmove", e => {
      if (e.touches.length > 0) {
        const rect = wrap.getBoundingClientRect();
        mouse.x = e.touches[0].clientX - rect.left;
        mouse.y = e.touches[0].clientY - rect.top;
        mouse.active = true;
      }
    }, { passive: true });

    wrap.addEventListener("touchend", () => {
      mouse.active = false;
      mouse.x = -9999;
      mouse.y = -9999;
    });

    let startTime = performance.now();

    function render(now) {
      const t = (now - startTime) * 0.001;
      ctx.clearRect(0, 0, width, height);

      // Random spark generator
      if (Math.random() < 0.18 && particles.length > 0) {
        const randomIdx = Math.floor(Math.random() * particles.length);
        particles[randomIdx].spark = 1.0;
      }

      // Update & Draw Particles
      const len = particles.length;
      for (let i = 0; i < len; i++) {
        const p = particles[i];

        // Idle micro-oscillation
        const idleX = Math.sin(t * 1.5 + p.seed) * 1.5;
        const idleY = Math.cos(t * 1.2 + p.seed) * 1.5;

        // Interaction with mouse
        if (mouse.active) {
          const dx = p.x - mouse.x;
          const dy = p.y - mouse.y;
          const dist = Math.hypot(dx, dy);

          if (dist < mouse.radius) {
            const force = (1 - dist / mouse.radius) * 18;
            const angle = Math.atan2(dy, dx);
            p.vx += Math.cos(angle) * force * 0.15;
            p.vy += Math.sin(angle) * force * 0.15;
            p.alpha = Math.min(1.0, p.alpha + 0.4);
            p.spark = Math.max(p.spark, 0.7);
          }
        }

        // Spring restitution back to origin
        const homeX = p.originX + idleX;
        const homeY = p.originY + idleY;
        const springX = (homeX - p.x) * 0.08;
        const springY = (homeY - p.y) * 0.08;

        p.vx = (p.vx + springX) * 0.84;
        p.vy = (p.vy + springY) * 0.84;

        p.x += p.vx;
        p.y += p.vy;

        // Spark and alpha decay
        if (p.spark > 0) p.spark -= 0.025;
        if (p.spark < 0) p.spark = 0;
        p.alpha += (p.baseAlpha - p.alpha) * 0.05;

        // Color calculation
        let fill;
        let effectiveAlpha = Math.min(1.0, p.alpha + p.spark * 0.7);

        if (p.colorType === "red" || p.spark > 0.4) {
          fill = `rgba(239, 68, 68, ${effectiveAlpha})`;
        } else if (p.colorType === "white") {
          fill = `rgba(255, 255, 255, ${effectiveAlpha})`;
        } else {
          fill = `rgba(161, 161, 170, ${effectiveAlpha * 0.8})`;
        }

        ctx.beginPath();
        const r = p.radius + (p.spark > 0 ? p.spark * 1.5 : 0);
        ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
        ctx.fillStyle = fill;
        ctx.fill();

        // Proximity web connections
        if (effectiveAlpha > 0.3) {
          for (let j = i + 1; j < Math.min(i + 12, len); j++) {
            const p2 = particles[j];
            const pdist = Math.hypot(p.x - p2.x, p.y - p2.y);
            if (pdist < 32) {
              const lineAlpha = (1 - pdist / 32) * effectiveAlpha * 0.45;
              ctx.beginPath();
              ctx.moveTo(p.x, p.y);
              ctx.lineTo(p2.x, p2.y);
              ctx.strokeStyle = p.colorType === "red" || p2.colorType === "red"
                ? `rgba(239, 68, 68, ${lineAlpha})`
                : `rgba(255, 255, 255, ${lineAlpha * 0.7})`;
              ctx.lineWidth = 0.8;
              ctx.stroke();
            }
          }
        }
      }

      requestAnimationFrame(render);
    }

    requestAnimationFrame(render);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initCanvasText);
  } else {
    initCanvasText();
  }
})();
