/**
 * Carousel functionality - yes, it actually works!
 */

document.addEventListener('DOMContentLoaded', () => {
    const carousel = document.getElementById('carousel');
    const track = carousel.querySelector('.carousel-track');
    const items = Array.from(track.children);
    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');
    const dotsContainer = document.getElementById('carouselDots');

    let currentIndex = 0;
    let isDragging = false;
    let startPos = 0;
    let currentTranslate = 0;
    let prevTranslate = 0;

    // Calculate items per view based on screen size
    function getItemsPerView() {
        if (window.innerWidth < 768) return 1;
        if (window.innerWidth < 1024) return 2;
        return 3;
    }

    let itemsPerView = getItemsPerView();
    const maxIndex = Math.max(0, items.length - itemsPerView);

    // Create dots
    function createDots() {
        dotsContainer.innerHTML = '';
        for (let i = 0; i <= maxIndex; i++) {
            const dot = document.createElement('div');
            dot.className = 'carousel-dot';
            if (i === currentIndex) dot.classList.add('active');
            dot.addEventListener('click', () => goToSlide(i));
            dotsContainer.appendChild(dot);
        }
    }

    // Update dots
    function updateDots() {
        const dots = dotsContainer.querySelectorAll('.carousel-dot');
        dots.forEach((dot, index) => {
            dot.classList.toggle('active', index === currentIndex);
        });
    }

    // Go to specific slide
    function goToSlide(index) {
        currentIndex = Math.max(0, Math.min(index, maxIndex));
        updateCarousel();
        updateDots();
    }

    // Update carousel position
    function updateCarousel() {
        const itemWidth = items[0].offsetWidth;
        const gap = 32; // match CSS gap
        const offset = -(itemWidth + gap) * currentIndex;
        track.style.transform = `translateX(${offset}px)`;
    }

    // Next slide
    function nextSlide() {
        if (currentIndex < maxIndex) {
            currentIndex++;
            updateCarousel();
            updateDots();
        }
    }

    // Previous slide
    function prevSlide() {
        if (currentIndex > 0) {
            currentIndex--;
            updateCarousel();
            updateDots();
        }
    }

    // Button click handlers
    nextBtn.addEventListener('click', nextSlide);
    prevBtn.addEventListener('click', prevSlide);

    // Keyboard navigation
    document.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowLeft') prevSlide();
        if (e.key === 'ArrowRight') nextSlide();
    });

    // Touch/Mouse drag handlers
    track.addEventListener('mousedown', dragStart);
    track.addEventListener('touchstart', dragStart);
    track.addEventListener('mouseup', dragEnd);
    track.addEventListener('touchend', dragEnd);
    track.addEventListener('mousemove', drag);
    track.addEventListener('touchmove', drag);
    track.addEventListener('mouseleave', dragEnd);

    function dragStart(e) {
        isDragging = true;
        startPos = getPositionX(e);
        track.style.cursor = 'grabbing';
        track.style.transition = 'none';
    }

    function drag(e) {
        if (!isDragging) return;
        e.preventDefault();

        const currentPosition = getPositionX(e);
        const diff = currentPosition - startPos;

        // Calculate current translate based on index
        const itemWidth = items[0].offsetWidth;
        const gap = 32;
        const baseTranslate = -(itemWidth + gap) * currentIndex;

        currentTranslate = baseTranslate + diff;
        track.style.transform = `translateX(${currentTranslate}px)`;
    }

    function dragEnd() {
        if (!isDragging) return;
        isDragging = false;
        track.style.cursor = 'grab';
        track.style.transition = 'transform 0.5s cubic-bezier(0.4, 0, 0.2, 1)';

        const movedBy = currentTranslate - prevTranslate;

        // Determine if we should move to next/prev slide
        if (movedBy < -100 && currentIndex < maxIndex) {
            currentIndex++;
        } else if (movedBy > 100 && currentIndex > 0) {
            currentIndex--;
        }

        updateCarousel();
        updateDots();
        prevTranslate = currentTranslate;
    }

    function getPositionX(e) {
        return e.type.includes('mouse') ? e.pageX : e.touches[0].clientX;
    }

    // Auto-play (optional)
    let autoplayInterval;

    function startAutoplay() {
        autoplayInterval = setInterval(() => {
            if (currentIndex < maxIndex) {
                nextSlide();
            } else {
                currentIndex = 0;
                updateCarousel();
                updateDots();
            }
        }, 5000);
    }

    function stopAutoplay() {
        clearInterval(autoplayInterval);
    }

    // Pause autoplay on interaction
    carousel.addEventListener('mouseenter', stopAutoplay);
    carousel.addEventListener('mouseleave', startAutoplay);

    // Handle window resize
    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            itemsPerView = getItemsPerView();
            const newMaxIndex = Math.max(0, items.length - itemsPerView);

            if (currentIndex > newMaxIndex) {
                currentIndex = newMaxIndex;
            }

            createDots();
            updateCarousel();
        }, 250);
    });

    // Initialize
    createDots();
    updateCarousel();
    startAutoplay();

    // Add ripple effect to buttons
    [prevBtn, nextBtn].forEach(btn => {
        btn.addEventListener('click', function(e) {
            const ripple = document.createElement('span');
            ripple.classList.add('ripple');

            const rect = this.getBoundingClientRect();
            const size = Math.max(rect.width, rect.height);
            const x = e.clientX - rect.left - size / 2;
            const y = e.clientY - rect.top - size / 2;

            ripple.style.width = ripple.style.height = size + 'px';
            ripple.style.left = x + 'px';
            ripple.style.top = y + 'px';

            this.appendChild(ripple);

            setTimeout(() => ripple.remove(), 600);
        });
    });
});
