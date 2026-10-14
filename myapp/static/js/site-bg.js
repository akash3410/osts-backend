/* =========================================================
   Full-site animated background: particle constellation.
   Draws into #heroParticles inside .site-bg (css/site-bg.js styles).
   Shared by the public pages (myapp/layout.html) and the
   auth page (userapp/auth_base.html). Respects prefers-reduced-motion.
   ========================================================= */
(function () {
    var canvas = document.getElementById('heroParticles');
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var particles = [], w = 0, h = 0, raf = null, mouse = { x: -9999, y: -9999 };
    var COUNT_BASE = 90, LINK_DIST = 120;

    function resize() {
        w = canvas.width = window.innerWidth;
        h = canvas.height = window.innerHeight;
        var count = Math.min(COUNT_BASE, Math.round((w * h) / 16000));
        particles = [];
        for (var i = 0; i < count; i++) {
            particles.push({
                x: Math.random() * w,
                y: Math.random() * h,
                vx: (Math.random() - 0.5) * 0.45,
                vy: (Math.random() - 0.5) * 0.45,
                r: Math.random() * 1.6 + 0.6
            });
        }
    }

    function draw() {
        ctx.clearRect(0, 0, w, h);
        for (var i = 0; i < particles.length; i++) {
            var p = particles[i];
            if (!reduced) {
                p.x += p.vx; p.y += p.vy;
                var dx = p.x - mouse.x, dy = p.y - mouse.y;
                var d2 = dx * dx + dy * dy;
                if (d2 < 14000 && d2 > 0.01) {
                    var f = (14000 - d2) / 14000 * 0.6;
                    var dist = Math.sqrt(d2);
                    p.x += (dx / dist) * f;
                    p.y += (dy / dist) * f;
                }
                if (p.x < 0) p.x = w; else if (p.x > w) p.x = 0;
                if (p.y < 0) p.y = h; else if (p.y > h) p.y = 0;
            }
            for (var j = i + 1; j < particles.length; j++) {
                var q = particles[j];
                var lx = p.x - q.x, ly = p.y - q.y;
                var ld = Math.sqrt(lx * lx + ly * ly);
                if (ld < LINK_DIST) {
                    ctx.strokeStyle = 'rgba(165, 200, 255, ' + (0.28 * (1 - ld / LINK_DIST)).toFixed(3) + ')';
                    ctx.lineWidth = 0.6;
                    ctx.beginPath();
                    ctx.moveTo(p.x, p.y);
                    ctx.lineTo(q.x, q.y);
                    ctx.stroke();
                }
            }
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(200, 224, 255, 0.55)';
            ctx.fill();
        }
        if (!reduced) raf = requestAnimationFrame(draw);
    }

    document.addEventListener('mousemove', function (e) {
        mouse.x = e.clientX;
        mouse.y = e.clientY;
    });
    document.addEventListener('mouseleave', function () {
        mouse.x = -9999; mouse.y = -9999;
    });

    var rt;
    window.addEventListener('resize', function () {
        clearTimeout(rt);
        rt = setTimeout(function () { resize(); if (reduced) draw(); }, 200);
    });

    resize();
    draw();
})();
