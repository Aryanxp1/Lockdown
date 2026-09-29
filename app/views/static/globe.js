/**
 * Lockdown — Interactive 3D Consensus Globe
 * Zero-dependency WebGL/Canvas 3D globe visualization representing
 * global hackathon nodes, judging panels, and consensus networks.
 */

(function () {
  function initGlobe() {
    const canvas = document.getElementById("lockdown-globe");
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let width, height, radius, cx, cy;
    let dpr = window.devicePixelRatio || 1;

    function resize() {
      const rect = canvas.getBoundingClientRect();
      width = rect.width || 540;
      height = rect.height || 540;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.scale(dpr, dpr);
      cx = width / 2;
      cy = height / 2;
      radius = Math.min(width, height) * 0.40;
    }
    resize();
    window.addEventListener("resize", resize);

    // Rotation state
    let rotX = 0.25;
    let rotY = -0.6;
    let targetRotX = rotX;
    let targetRotY = rotY;
    let isDragging = false;
    let startX = 0;
    let startY = 0;
    let autoRotate = true;

    // Major competition & judging hubs (lat, lng, name)
    const HUBS = [
      { lat: 37.7749, lng: -122.4194, name: "San Francisco" },
      { lat: 40.7128, lng: -74.0060, name: "New York" },
      { lat: 51.5074, lng: -0.1278, name: "London" },
      { lat: 52.5200, lng: 13.4050, name: "Berlin" },
      { lat: 47.3769, lng: 8.5417, name: "Zurich" },
      { lat: 12.9716, lng: 77.5946, name: "Bengaluru" },
      { lat: 1.3521, lng: 103.8198, name: "Singapore" },
      { lat: 35.6762, lng: 139.6503, name: "Tokyo" },
      { lat: -33.8688, lng: 151.2093, name: "Sydney" },
      { lat: -23.5505, lng: -46.6333, name: "São Paulo" },
      { lat: 38.7223, lng: -9.1393, name: "Lisbon" },
      { lat: 25.2048, lng: 55.2708, name: "Dubai" },
      { lat: 43.6532, lng: -79.3832, name: "Toronto" },
      { lat: 37.5665, lng: 126.9780, name: "Seoul" },
    ];

    // Network consensus arcs between hubs (Crimson Red, Stark White & Slate)
    const ARCS = [
      { from: 0, to: 2, color: "#ef4444", speed: 0.0009 },  // SF -> London
      { from: 1, to: 3, color: "#ffffff", speed: 0.0011 },  // NY -> Berlin
      { from: 2, to: 5, color: "#f87171", speed: 0.0008 },  // London -> Bengaluru
      { from: 5, to: 7, color: "#e4e4e7", speed: 0.0013 },  // Bengaluru -> Tokyo
      { from: 7, to: 0, color: "#ef4444", speed: 0.0007 },  // Tokyo -> SF
      { from: 4, to: 6, color: "#fca5a5", speed: 0.0010 },  // Zurich -> Singapore
      { from: 0, to: 8, color: "#ffffff", speed: 0.0009 },  // SF -> Sydney
      { from: 9, to: 10, color: "#dc2626", speed: 0.0012 }, // São Paulo -> Lisbon
      { from: 1, to: 11, color: "#ef4444", speed: 0.0009 }, // NY -> Dubai
      { from: 6, to: 13, color: "#ffffff", speed: 0.0014 }, // Singapore -> Seoul
      { from: 12, to: 2, color: "#f87171", speed: 0.0010 }, // Toronto -> London
    ];

    // Generate realistic continent dots
    // Bounding boxes of major continents: [minLat, maxLat, minLng, maxLng]
    const CONTINENT_BOXES = [
      // North America
      [25, 65, -125, -70],
      [15, 30, -115, -85],
      // South America
      [-50, 10, -78, -35],
      // Europe
      [36, 65, -10, 40],
      [55, 70, 5, 30],
      // Africa
      [-34, 35, -17, 50],
      // Asia
      [10, 70, 45, 140],
      [5, 30, 70, 95], // India
      [20, 45, 100, 130], // East Asia
      [-10, 10, 95, 140], // SE Asia
      // Australia & Oceania
      [-40, -12, 115, 153],
      [-45, -35, 166, 178], // NZ
      // Japan & UK
      [31, 45, 130, 145],
      [50, 59, -8, 2],
    ];

    function isLand(lat, lng) {
      for (let i = 0; i < CONTINENT_BOXES.length; i++) {
        const b = CONTINENT_BOXES[i];
        if (lat >= b[0] && lat <= b[1] && lng >= b[2] && lng <= b[3]) {
          return true;
        }
      }
      return false;
    }

    const DOTS = [];
    // Sample points across the globe using Fibonacci sphere
    const TOTAL_SAMPLES = 2800;
    const phi = Math.PI * (3 - Math.sqrt(5));

    for (let i = 0; i < TOTAL_SAMPLES; i++) {
      const y = 1 - (i / (TOTAL_SAMPLES - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      const theta = phi * i;

      const x = Math.cos(theta) * r;
      const z = Math.sin(theta) * r;

      // Convert (x, y, z) to lat/lng
      const lat = Math.asin(y) * (180 / Math.PI);
      const lng = Math.atan2(z, x) * (180 / Math.PI);

      if (isLand(lat, lng)) {
        DOTS.push({ lat, lng, x, y, z });
      }
    }

    function latLngToVector(lat, lng, r) {
      const phi = (90 - lat) * (Math.PI / 180);
      const theta = (lng + 180) * (Math.PI / 180);
      const x = -(r * Math.sin(phi) * Math.cos(theta));
      const z = r * Math.sin(phi) * Math.sin(theta);
      const y = r * Math.cos(phi);
      return { x, y, z };
    }

    // Convert hubs to vectors
    const hubPoints = HUBS.map(h => ({
      ...h,
      ...latLngToVector(h.lat, h.lng, 1)
    }));

    // Mouse / Touch Drag Handlers
    canvas.addEventListener("mousedown", e => {
      isDragging = true;
      startX = e.clientX;
      startY = e.clientY;
      autoRotate = false;
    });

    window.addEventListener("mousemove", e => {
      if (!isDragging) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      startX = e.clientX;
      startY = e.clientY;
      targetRotY += dx * 0.006;
      targetRotX = Math.max(-0.8, Math.min(0.8, targetRotX - dy * 0.006));
    });

    window.addEventListener("mouseup", () => {
      isDragging = false;
      setTimeout(() => { autoRotate = true; }, 2500);
    });

    canvas.addEventListener("touchstart", e => {
      if (e.touches.length === 1) {
        isDragging = true;
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
        autoRotate = false;
      }
    }, { passive: true });

    window.addEventListener("touchmove", e => {
      if (!isDragging || e.touches.length !== 1) return;
      const dx = e.touches[0].clientX - startX;
      const dy = e.touches[0].clientY - startY;
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
      targetRotY += dx * 0.008;
      targetRotX = Math.max(-0.8, Math.min(0.8, targetRotX - dy * 0.008));
    }, { passive: true });

    window.addEventListener("touchend", () => {
      isDragging = false;
      setTimeout(() => { autoRotate = true; }, 2500);
    });

    // 3D coordinate rotation
    function rotatePoint(p, cosX, sinX, cosY, sinY) {
      // Rotate Y
      const x1 = p.x * cosY - p.z * sinY;
      const z1 = p.x * sinY + p.z * cosY;

      // Rotate X
      const y2 = p.y * cosX - z1 * sinX;
      const z2 = p.y * sinX + z1 * cosX;

      return { x: x1, y: y2, z: z2 };
    }

    let startTime = Date.now();

    function render() {
      const now = Date.now();
      const elapsed = (now - startTime) / 1000;

      if (autoRotate && !isDragging) {
        targetRotY += 0.003;
      }

      // Smooth damping
      rotX += (targetRotX - rotX) * 0.08;
      rotY += (targetRotY - rotY) * 0.08;

      ctx.clearRect(0, 0, width, height);

      const cosX = Math.cos(rotX);
      const sinX = Math.sin(rotX);
      const cosY = Math.cos(rotY);
      const sinY = Math.sin(rotY);

      // 1. Sphere ambient background & rim atmosphere
      const sphereGrad = ctx.createRadialGradient(
        cx - radius * 0.3,
        cy - radius * 0.3,
        radius * 0.1,
        cx,
        cy,
        radius
      );
      sphereGrad.addColorStop(0, "#121218");
      sphereGrad.addColorStop(0.7, "#08080c");
      sphereGrad.addColorStop(1, "#040406");

      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.fillStyle = sphereGrad;
      ctx.fill();

      // Atmospheric glowing rim (Crimson Red)
      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.lineWidth = 2.2;
      ctx.strokeStyle = "rgba(239, 68, 68, 0.4)";
      ctx.shadowColor = "#ef4444";
      ctx.shadowBlur = 18;
      ctx.stroke();
      ctx.restore();

      // 2. Render Landmass Dots (Monochrome Silver & Dark Zinc)
      for (let i = 0; i < DOTS.length; i++) {
        const d = DOTS[i];
        const rPt = rotatePoint(d, cosX, sinX, cosY, sinY);

        // Projected 2D
        const px = cx + rPt.x * radius;
        const py = cy - rPt.y * radius;

        if (rPt.z > 0) {
          // Front hemisphere
          const alpha = 0.25 + (rPt.z * 0.7);
          const size = 1.0 + (rPt.z * 0.9);
          ctx.beginPath();
          ctx.arc(px, py, size, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(228, 228, 231, ${alpha})`;
          ctx.fill();
        } else {
          // Back hemisphere (subtle depth)
          const alpha = Math.max(0.04, 0.12 + (rPt.z * 0.1));
          ctx.beginPath();
          ctx.arc(px, py, 0.9, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(63, 63, 70, ${alpha})`;
          ctx.fill();
        }
      }

      // 3. Render Hubs & Ripple Rings (Stark White & Red Ripple)
      const rotatedHubs = hubPoints.map((h, idx) => {
        const rPt = rotatePoint(h, cosX, sinX, cosY, sinY);
        return {
          ...h,
          idx,
          rPt,
          px: cx + rPt.x * radius,
          py: cy - rPt.y * radius,
          visible: rPt.z > -0.1
        };
      });

      for (let i = 0; i < rotatedHubs.length; i++) {
        const h = rotatedHubs[i];
        if (!h.visible) continue;

        const alpha = Math.min(1, Math.max(0.2, h.rPt.z + 0.3));

        // Hub core
        ctx.beginPath();
        ctx.arc(h.px, h.py, 3, 0, Math.PI * 2);
        ctx.fillStyle = "#ffffff";
        ctx.shadowColor = "#ef4444";
        ctx.shadowBlur = 10;
        ctx.fill();
        ctx.shadowBlur = 0;

        // Pulsing ripple ring
        const ringProgress = ((now * 0.0015 + i * 0.4) % 1.0);
        const ringRadius = 3 + ringProgress * 12;
        const ringAlpha = (1 - ringProgress) * 0.7 * alpha;

        ctx.beginPath();
        ctx.arc(h.px, h.py, ringRadius, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(239, 68, 68, ${ringAlpha})`;
        ctx.lineWidth = 1.2;
        ctx.stroke();
      }

      // 4. Render 3D Great-Circle Arcs with Traveling Light Beams
      for (let i = 0; i < ARCS.length; i++) {
        const arc = ARCS[i];
        const h1 = rotatedHubs[arc.from];
        const h2 = rotatedHubs[arc.to];

        if (!h1 || !h2) continue;

        // Midpoint elevation (arc height)
        const p1 = h1.rPt;
        const p2 = h2.rPt;

        // Calculate arc samples in 3D
        const ARC_STEPS = 28;
        const pts = [];
        let allHidden = true;

        for (let s = 0; s <= ARC_STEPS; s++) {
          const t = s / ARC_STEPS;
          // Spherical linear interpolation approximation
          const ix = p1.x * (1 - t) + p2.x * t;
          const iy = p1.y * (1 - t) + p2.y * t;
          const iz = p1.z * (1 - t) + p2.z * t;
          const len = Math.sqrt(ix * ix + iy * iy + iz * iz) || 1;

          // Arch altitude
          const alt = 1 + Math.sin(t * Math.PI) * 0.22;
          const r = (radius * alt) / len;

          const px = cx + ix * r;
          const py = cy - iy * r;
          const pz = iz;

          if (pz > -0.2) allHidden = false;
          pts.push({ px, py, pz, t });
        }

        if (allHidden) continue;

        // Draw arc path
        ctx.beginPath();
        let started = false;
        for (let s = 0; s < pts.length; s++) {
          const pt = pts[s];
          if (pt.pz < -0.15) {
            started = false;
            continue;
          }
          if (!started) {
            ctx.moveTo(pt.px, pt.py);
            started = true;
          } else {
            ctx.lineTo(pt.px, pt.py);
          }
        }
        ctx.lineWidth = 1.2;
        ctx.strokeStyle = `rgba(239, 68, 68, 0.22)`;
        ctx.stroke();

        // Traveling light pulse
        const headT = (now * arc.speed + i * 0.23) % 1.0;
        const pulseIndex = Math.floor(headT * ARC_STEPS);
        const pulsePt = pts[pulseIndex];

        if (pulsePt && pulsePt.pz > -0.1) {
          ctx.save();
          ctx.beginPath();
          ctx.arc(pulsePt.px, pulsePt.py, 3, 0, Math.PI * 2);
          ctx.fillStyle = arc.color;
          ctx.shadowColor = arc.color;
          ctx.shadowBlur = 12;
          ctx.fill();
          ctx.restore();
        }
      }

      requestAnimationFrame(render);
    }

    render();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initGlobe);
  } else {
    initGlobe();
  }
})();
