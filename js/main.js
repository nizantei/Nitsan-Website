/**
 * Main JavaScript - Core Functionality
 * Digital Craftsman Portfolio
 */

document.addEventListener('DOMContentLoaded', () => {
    console.log('%c🎨 Digital Craftsman', 'color: #00d4ff; font-size: 24px; font-weight: bold;');
    console.log('%cBuilt with vanilla JS, no frameworks needed', 'color: #8892b0; font-size: 12px;');

    initCustomCursor();
    initStatsCounter();
    initSmoothScroll();
    initMagneticButtons();
    initContactButton();
    initInteractiveBlob();
});

/**
 * Custom cursor
 */
function initCustomCursor() {
    // Skip on mobile
    if (window.innerWidth <= 768) return;

    const cursorDot = document.querySelector('.cursor-dot');
    const cursorRing = document.querySelector('.cursor-ring');

    if (!cursorDot || !cursorRing) return;

    let mouseX = 0;
    let mouseY = 0;
    let dotX = 0;
    let dotY = 0;
    let ringX = 0;
    let ringY = 0;

    // Track mouse position
    document.addEventListener('mousemove', (e) => {
        mouseX = e.clientX;
        mouseY = e.clientY;
    });

    // Smooth cursor follow
    function animate() {
        // Dot follows quickly
        dotX += (mouseX - dotX) * 0.3;
        dotY += (mouseY - dotY) * 0.3;

        // Ring follows with delay
        ringX += (mouseX - ringX) * 0.15;
        ringY += (mouseY - ringY) * 0.15;

        cursorDot.style.transform = `translate(${dotX}px, ${dotY}px)`;
        cursorRing.style.transform = `translate(${ringX - 16}px, ${ringY - 16}px)`;

        requestAnimationFrame(animate);
    }

    animate();

    // Scale up on interactive elements
    const interactiveElements = document.querySelectorAll('a, button, .bento-item, .carousel-btn');

    interactiveElements.forEach(el => {
        el.addEventListener('mouseenter', () => {
            cursorDot.style.transform += ' scale(1.5)';
            cursorRing.style.transform += ' scale(1.5)';
        });

        el.addEventListener('mouseleave', () => {
            cursorDot.style.transform = `translate(${dotX}px, ${dotY}px)`;
            cursorRing.style.transform = `translate(${ringX - 16}px, ${ringY - 16}px)`;
        });
    });
}

/**
 * Animated stats counter
 */
function initStatsCounter() {
    const statNumbers = document.querySelectorAll('.stat-number');

    statNumbers.forEach(stat => {
        const target = parseInt(stat.getAttribute('data-target'));
        let current = 0;
        const increment = target / 100;
        const duration = 2000; // 2 seconds
        const stepTime = duration / 100;

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const counter = setInterval(() => {
                        current += increment;
                        if (current >= target) {
                            stat.textContent = target;
                            clearInterval(counter);
                        } else {
                            stat.textContent = Math.floor(current);
                        }
                    }, stepTime);

                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.5 });

        observer.observe(stat);
    });
}

/**
 * Smooth scrolling for anchor links
 */
function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const targetId = this.getAttribute('href');

            if (targetId === '#') {
                window.scrollTo({
                    top: 0,
                    behavior: 'smooth'
                });
                return;
            }

            const targetElement = document.querySelector(targetId);
            if (targetElement) {
                targetElement.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
}

/**
 * Magnetic effect on buttons
 */
function initMagneticButtons() {
    const buttons = document.querySelectorAll('.contact-button, .carousel-btn');

    buttons.forEach(button => {
        button.addEventListener('mousemove', function(e) {
            const rect = this.getBoundingClientRect();
            const x = e.clientX - rect.left - rect.width / 2;
            const y = e.clientY - rect.top - rect.height / 2;

            this.style.transform = `translate(${x * 0.2}px, ${y * 0.2}px)`;
        });

        button.addEventListener('mouseleave', function() {
            this.style.transform = '';
        });
    });
}

/**
 * Contact button interactions
 */
function initContactButton() {
    const contactButton = document.querySelector('.contact-button');

    if (!contactButton) return;

    contactButton.addEventListener('click', function(e) {
        // Create ripple effect
        const ripple = document.createElement('span');
        ripple.className = 'ripple';

        const rect = this.getBoundingClientRect();
        const size = Math.max(rect.width, rect.height);
        const x = e.clientX - rect.left - size / 2;
        const y = e.clientY - rect.top - size / 2;

        ripple.style.width = ripple.style.height = size + 'px';
        ripple.style.left = x + 'px';
        ripple.style.top = y + 'px';

        this.appendChild(ripple);

        setTimeout(() => ripple.remove(), 600);

        // Log click (for analytics if needed)
        console.log('💌 Contact button clicked!');
    });
}

/**
 * Parallax effect on scroll
 */
function initParallax() {
    const parallaxElements = document.querySelectorAll('.hero');

    let ticking = false;

    window.addEventListener('scroll', () => {
        if (!ticking) {
            window.requestAnimationFrame(() => {
                const scrolled = window.pageYOffset;

                parallaxElements.forEach(el => {
                    const speed = 0.5;
                    el.style.transform = `translateY(${scrolled * speed}px)`;
                });

                ticking = false;
            });

            ticking = true;
        }
    });
}

// Initialize parallax
initParallax();

/**
 * Add tilt effect to bento items (mouse and touch)
 */
document.querySelectorAll('.bento-item').forEach(item => {
    function updateTilt(clientX, clientY) {
        const rect = item.getBoundingClientRect();
        const x = clientX - rect.left;
        const y = clientY - rect.top;

        const centerX = rect.width / 2;
        const centerY = rect.height / 2;

        const rotateX = (y - centerY) / 10;
        const rotateY = (centerX - x) / 10;

        item.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-8px)`;
    }

    function resetTilt() {
        item.style.transform = '';
    }

    // Mouse events
    item.addEventListener('mousemove', function(e) {
        updateTilt(e.clientX, e.clientY);
    });

    item.addEventListener('mouseleave', resetTilt);

    // Touch events for mobile
    item.addEventListener('touchmove', function(e) {
        const touch = e.touches[0];
        updateTilt(touch.clientX, touch.clientY);
    });

    item.addEventListener('touchend', resetTilt);
});

/**
 * Gradient card interactive effect (mouse and touch)
 */
document.querySelectorAll('.gradient-card').forEach(card => {
    function updateGradient(clientX, clientY) {
        const rect = card.getBoundingClientRect();
        const x = ((clientX - rect.left) / rect.width) * 100;
        const y = ((clientY - rect.top) / rect.height) * 100;

        card.style.background = `
            radial-gradient(circle at ${x}% ${y}%,
                var(--color-gradient-1),
                var(--color-gradient-2)
            )
        `;
    }

    function resetGradient() {
        card.style.background = '';
    }

    // Mouse events
    card.addEventListener('mousemove', function(e) {
        updateGradient(e.clientX, e.clientY);
    });

    card.addEventListener('mouseleave', resetGradient);

    // Touch events for mobile
    card.addEventListener('touchmove', function(e) {
        e.preventDefault();
        const touch = e.touches[0];
        updateGradient(touch.clientX, touch.clientY);
    });

    card.addEventListener('touchend', resetGradient);
});

/**
 * Interactive blob with eyes that follow cursor/touch
 */
function initInteractiveBlob() {
    const blob = document.getElementById('interactiveBlob');
    if (!blob) return;

    const leftEye = blob.querySelector('.blob-eye.left');
    const rightEye = blob.querySelector('.blob-eye.right');

    if (!leftEye || !rightEye) return;

    const blobContainer = blob.parentElement;

    function updateBlobEyes(clientX, clientY) {
        const rect = blob.getBoundingClientRect();
        const blobCenterX = rect.left + rect.width / 2;
        const blobCenterY = rect.top + rect.height / 2;

        // Calculate angle to pointer
        const angle = Math.atan2(
            clientY - blobCenterY,
            clientX - blobCenterX
        );

        // Move pupils
        const distance = 3; // Distance pupils can move
        const pupilX = Math.cos(angle) * distance;
        const pupilY = Math.sin(angle) * distance;

        leftEye.style.setProperty('--pupil-x', `${pupilX}px`);
        leftEye.style.setProperty('--pupil-y', `${pupilY}px`);
        rightEye.style.setProperty('--pupil-x', `${pupilX}px`);
        rightEye.style.setProperty('--pupil-y', `${pupilY}px`);

        // Also rotate blob slightly toward pointer
        const rotateX = (clientY - blobCenterY) / 10;
        const rotateY = (clientX - blobCenterX) / 10;

        blob.style.transform = `rotateX(${-rotateX}deg) rotateY(${rotateY}deg) scale(1.05)`;
    }

    function resetBlob() {
        leftEye.style.setProperty('--pupil-x', '0px');
        leftEye.style.setProperty('--pupil-y', '0px');
        rightEye.style.setProperty('--pupil-x', '0px');
        rightEye.style.setProperty('--pupil-y', '0px');
        blob.style.transform = '';
    }

    // Mouse events
    blobContainer.addEventListener('mousemove', (e) => {
        updateBlobEyes(e.clientX, e.clientY);
    });

    blobContainer.addEventListener('mouseleave', resetBlob);

    // Touch events for mobile
    blobContainer.addEventListener('touchmove', (e) => {
        e.preventDefault();
        const touch = e.touches[0];
        updateBlobEyes(touch.clientX, touch.clientY);
    });

    blobContainer.addEventListener('touchend', resetBlob);

    // Add CSS custom properties support
    const style = document.createElement('style');
    style.textContent = `
        .blob-eye::before {
            transform: translate(var(--pupil-x, 0px), var(--pupil-y, 0px));
        }
    `;
    document.head.appendChild(style);
}

/**
 * Konami code easter egg
 */
let konamiCode = [];
const konamiSequence = ['ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight', 'b', 'a'];

document.addEventListener('keydown', (e) => {
    konamiCode.push(e.key);

    if (konamiCode.length > 10) {
        konamiCode.shift();
    }

    if (konamiCode.join(',') === konamiSequence.join(',')) {
        activateEasterEgg();
        konamiCode = [];
    }
});

function activateEasterEgg() {
    console.log('%c🎮 KONAMI CODE!', 'color: #00d4ff; font-size: 30px; font-weight: bold;');

    // Add party mode
    document.body.style.animation = 'rainbow-bg 2s linear';

    const style = document.createElement('style');
    style.textContent = `
        @keyframes rainbow-bg {
            0% { filter: hue-rotate(0deg); }
            100% { filter: hue-rotate(360deg); }
        }
    `;
    document.head.appendChild(style);

    setTimeout(() => {
        document.body.style.animation = '';
    }, 2000);
}

/**
 * Performance monitoring
 */
window.addEventListener('load', () => {
    if ('performance' in window) {
        const perfData = performance.getEntriesByType('navigation')[0];

        console.log('%c⚡ Performance', 'color: #00d4ff; font-weight: bold;');
        console.log(`Load time: ${Math.round(perfData.loadEventEnd - perfData.loadEventStart)}ms`);
        console.log(`DOM ready: ${Math.round(perfData.domContentLoadedEventEnd - perfData.domContentLoadedEventStart)}ms`);
    }
});

/**
 * Viewport height fix for mobile
 */
function setVH() {
    const vh = window.innerHeight * 0.01;
    document.documentElement.style.setProperty('--vh', `${vh}px`);
}

setVH();
window.addEventListener('resize', setVH);

/**
 * Detect dark mode preference (for future use)
 */
const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
console.log(`Color scheme: ${prefersDark ? 'dark' : 'light'}`);
