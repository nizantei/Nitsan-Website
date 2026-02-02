/**
 * Floating particles background effect
 */

document.addEventListener('DOMContentLoaded', () => {
    const particlesContainer = document.getElementById('particles');

    if (!particlesContainer) return;

    const particleCount = window.innerWidth < 768 ? 30 : 50;
    const particles = [];

    class Particle {
        constructor() {
            this.x = Math.random() * window.innerWidth;
            this.y = Math.random() * window.innerHeight;
            this.size = Math.random() * 3 + 1;
            this.speedX = (Math.random() - 0.5) * 0.5;
            this.speedY = (Math.random() - 0.5) * 0.5;
            this.opacity = Math.random() * 0.5 + 0.2;

            // Create DOM element
            this.element = document.createElement('div');
            this.element.className = 'particle';
            this.element.style.cssText = `
                width: ${this.size}px;
                height: ${this.size}px;
                background: rgba(0, 212, 255, ${this.opacity});
                box-shadow: 0 0 ${this.size * 2}px rgba(0, 212, 255, ${this.opacity});
                position: absolute;
                left: ${this.x}px;
                top: ${this.y}px;
                pointer-events: none;
            `;
            particlesContainer.appendChild(this.element);
        }

        update() {
            this.x += this.speedX;
            this.y += this.speedY;

            // Wrap around screen
            if (this.x > window.innerWidth) this.x = 0;
            if (this.x < 0) this.x = window.innerWidth;
            if (this.y > window.innerHeight) this.y = 0;
            if (this.y < 0) this.y = window.innerHeight;

            // Update DOM
            this.element.style.left = this.x + 'px';
            this.element.style.top = this.y + 'px';
        }
    }

    // Create particles
    for (let i = 0; i < particleCount; i++) {
        particles.push(new Particle());
    }

    // Animation loop
    function animate() {
        particles.forEach(particle => particle.update());
        requestAnimationFrame(animate);
    }

    animate();

    // Mouse interaction - particles follow mouse
    let mouseX = 0;
    let mouseY = 0;

    document.addEventListener('mousemove', (e) => {
        mouseX = e.clientX;
        mouseY = e.clientY;

        // Apply subtle attraction to nearby particles
        particles.forEach(particle => {
            const dx = mouseX - particle.x;
            const dy = mouseY - particle.y;
            const distance = Math.sqrt(dx * dx + dy * dy);

            if (distance < 150) {
                const force = (150 - distance) / 150;
                particle.speedX += (dx / distance) * force * 0.01;
                particle.speedY += (dy / distance) * force * 0.01;

                // Limit speed
                const speed = Math.sqrt(particle.speedX ** 2 + particle.speedY ** 2);
                if (speed > 2) {
                    particle.speedX = (particle.speedX / speed) * 2;
                    particle.speedY = (particle.speedY / speed) * 2;
                }
            }
        });
    });

    // Create connection lines between nearby particles
    function drawConnections() {
        const canvas = document.createElement('canvas');
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        canvas.style.position = 'fixed';
        canvas.style.top = '0';
        canvas.style.left = '0';
        canvas.style.pointerEvents = 'none';
        canvas.style.zIndex = '1';
        particlesContainer.appendChild(canvas);

        const ctx = canvas.getContext('2d');

        function draw() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            // Draw connections
            for (let i = 0; i < particles.length; i++) {
                for (let j = i + 1; j < particles.length; j++) {
                    const dx = particles[i].x - particles[j].x;
                    const dy = particles[i].y - particles[j].y;
                    const distance = Math.sqrt(dx * dx + dy * dy);

                    if (distance < 150) {
                        ctx.beginPath();
                        ctx.strokeStyle = `rgba(0, 212, 255, ${0.2 * (1 - distance / 150)})`;
                        ctx.lineWidth = 1;
                        ctx.moveTo(particles[i].x, particles[i].y);
                        ctx.lineTo(particles[j].x, particles[j].y);
                        ctx.stroke();
                    }
                }
            }

            requestAnimationFrame(draw);
        }

        draw();

        // Handle resize
        window.addEventListener('resize', () => {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        });
    }

    // Only draw connections on desktop
    if (window.innerWidth > 768) {
        drawConnections();
    }

    // Handle window resize
    window.addEventListener('resize', () => {
        // Update particle boundaries
        particles.forEach(particle => {
            if (particle.x > window.innerWidth) particle.x = window.innerWidth;
            if (particle.y > window.innerHeight) particle.y = window.innerHeight;
        });
    });
});

/**
 * Star field effect for hero section
 */
function createStarField() {
    const hero = document.querySelector('.hero');
    if (!hero) return;

    const starCount = 100;

    for (let i = 0; i < starCount; i++) {
        const star = document.createElement('div');
        star.className = 'star';
        star.style.cssText = `
            position: absolute;
            width: ${Math.random() * 2 + 1}px;
            height: ${Math.random() * 2 + 1}px;
            background: white;
            border-radius: 50%;
            left: ${Math.random() * 100}%;
            top: ${Math.random() * 100}%;
            opacity: ${Math.random() * 0.7 + 0.3};
            animation: twinkle ${Math.random() * 3 + 2}s ease-in-out infinite;
        `;
        hero.appendChild(star);
    }

    // Add twinkle animation
    const style = document.createElement('style');
    style.textContent = `
        @keyframes twinkle {
            0%, 100% { opacity: 0.3; }
            50% { opacity: 1; }
        }
    `;
    document.head.appendChild(style);
}

// Initialize star field
document.addEventListener('DOMContentLoaded', createStarField);
