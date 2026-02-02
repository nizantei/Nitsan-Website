/**
 * Scroll animations and effects
 */

document.addEventListener('DOMContentLoaded', () => {
    initScrollAnimations();
    initGlitchEffect();
});

/**
 * Initialize scroll-triggered animations
 */
function initScrollAnimations() {
    const animatedElements = document.querySelectorAll('.animate-on-scroll');

    // Check browser support
    if (!('IntersectionObserver' in window)) {
        // Fallback: show all elements
        animatedElements.forEach(el => el.classList.add('is-visible'));
        return;
    }

    // Create observer
    const observer = new IntersectionObserver(
        (entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('is-visible');
                    observer.unobserve(entry.target);
                }
            });
        },
        {
            threshold: 0.15,
            rootMargin: '0px 0px -100px 0px'
        }
    );

    // Observe all animated elements
    animatedElements.forEach(element => {
        observer.observe(element);
    });
}

/**
 * Glitch effect on hero title
 */
function initGlitchEffect() {
    const glitchElement = document.querySelector('.glitch');

    if (!glitchElement) return;

    // Random glitch triggers
    setInterval(() => {
        if (Math.random() > 0.7) {
            glitchElement.classList.add('glitch-active');

            setTimeout(() => {
                glitchElement.classList.remove('glitch-active');
            }, 200);
        }
    }, 3000);
}

/**
 * Parallax effect on scroll
 */
function initParallaxScroll() {
    const hero = document.querySelector('.hero');

    if (!hero) return;

    let ticking = false;

    window.addEventListener('scroll', () => {
        if (!ticking) {
            window.requestAnimationFrame(() => {
                const scrolled = window.pageYOffset;
                const parallaxSpeed = 0.5;

                hero.style.transform = `translateY(${scrolled * parallaxSpeed}px)`;

                ticking = false;
            });

            ticking = true;
        }
    });
}

// Initialize parallax
initParallaxScroll();

/**
 * Marquee auto-pause on hover
 */
document.querySelectorAll('.marquee-content').forEach(marquee => {
    marquee.addEventListener('mouseenter', function() {
        this.style.animationPlayState = 'paused';
    });

    marquee.addEventListener('mouseleave', function() {
        this.style.animationPlayState = 'running';
    });
});

/**
 * Add reveal animations to elements in viewport
 */
function revealOnScroll() {
    const reveals = document.querySelectorAll('.bento-item, .project-card');

    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry, index) => {
            if (entry.isIntersecting) {
                setTimeout(() => {
                    entry.target.style.opacity = '1';
                    entry.target.style.transform = 'translateY(0)';
                }, index * 100);

                observer.unobserve(entry.target);
            }
        });
    }, {
        threshold: 0.1
    });

    reveals.forEach(element => {
        element.style.opacity = '0';
        element.style.transform = 'translateY(30px)';
        element.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        observer.observe(element);
    });
}

// Removed to avoid conflict with existing animations
// revealOnScroll();

/**
 * Typing effect for hero subtitle
 */
function initTypingEffect() {
    const typingElement = document.querySelector('.typing-text');

    if (!typingElement) return;

    const text = typingElement.textContent;
    typingElement.textContent = '';

    let charIndex = 0;

    function type() {
        if (charIndex < text.length) {
            typingElement.textContent += text.charAt(charIndex);
            charIndex++;
            setTimeout(type, 50);
        }
    }

    // Start typing after a delay
    setTimeout(type, 500);
}

// Initialize typing effect
initTypingEffect();

/**
 * Blob morph animation variations
 */
function animateBlob() {
    const blobs = document.querySelectorAll('.blob');

    blobs.forEach(blob => {
        blob.addEventListener('mouseenter', function() {
            this.style.animation = 'morph 2s ease-in-out infinite';
        });

        blob.addEventListener('mouseleave', function() {
            this.style.animation = 'morph 8s ease-in-out infinite';
        });
    });
}

animateBlob();

/**
 * Smooth scroll progress indicator
 */
function createScrollProgress() {
    const progressBar = document.createElement('div');
    progressBar.className = 'scroll-progress';
    progressBar.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        height: 3px;
        background: linear-gradient(90deg, #00d4ff, #ff006e);
        z-index: 9999;
        transform-origin: left;
        transform: scaleX(0);
        transition: transform 0.1s ease-out;
        pointer-events: none;
    `;
    document.body.appendChild(progressBar);

    let ticking = false;

    window.addEventListener('scroll', () => {
        if (!ticking) {
            window.requestAnimationFrame(() => {
                const scrollHeight = document.documentElement.scrollHeight - window.innerHeight;
                const scrolled = window.pageYOffset / scrollHeight;

                progressBar.style.transform = `scaleX(${scrolled})`;

                ticking = false;
            });

            ticking = true;
        }
    });
}

// Uncomment to enable scroll progress
createScrollProgress();

/**
 * Add glow effect to elements on hover
 */
document.querySelectorAll('.contact-button').forEach(button => {
    button.addEventListener('mouseenter', function() {
        this.style.boxShadow = '0 0 40px rgba(0, 212, 255, 0.6), 0 0 60px rgba(255, 0, 110, 0.4)';
    });

    button.addEventListener('mouseleave', function() {
        this.style.boxShadow = '0 10px 40px rgba(0, 212, 255, 0.3)';
    });
});

/**
 * Stats counter animation improvement
 */
function animateStats() {
    const stats = document.querySelectorAll('.stat-number');

    stats.forEach(stat => {
        stat.addEventListener('mouseenter', function() {
            this.style.transform = 'scale(1.1)';
            this.style.color = 'var(--color-accent-2)';
        });

        stat.addEventListener('mouseleave', function() {
            this.style.transform = '';
            this.style.color = '';
        });
    });
}

animateStats();

/**
 * Window resize handler with debounce
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

const handleResize = debounce(() => {
    console.log('Window resized');
    // Re-calculate any size-dependent animations here
}, 250);

window.addEventListener('resize', handleResize);

/**
 * Performance optimization - remove will-change after animation
 */
document.querySelectorAll('.animate-on-scroll').forEach(element => {
    element.addEventListener('transitionend', function() {
        this.style.willChange = 'auto';
    });
});
