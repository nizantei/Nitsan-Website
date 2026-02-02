/**
 * Infinite Carousel - Smooth both directions
 */

document.addEventListener('DOMContentLoaded', () => {
    const carousel = document.getElementById('carousel');
    const track = carousel.querySelector('.carousel-track');
    const items = Array.from(track.children);
    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');
    const dotsContainer = document.getElementById('carouselDots');

    const itemCount = items.length;
    let currentIndex = 0;
    let isTransitioning = false;

    // Clone items for infinite effect
    function setupInfiniteCarousel() {
        // Clone all items twice (before and after)
        items.forEach(item => {
            const cloneBefore = item.cloneNode(true);
            const cloneAfter = item.cloneNode(true);
            track.insertBefore(cloneBefore, track.firstChild);
            track.appendChild(cloneAfter);
        });

        // Set initial position (centered on original items)
        currentIndex = itemCount;
        updateCarouselPosition(false);
    }

    // Get item width including gap
    function getItemWidth() {
        const item = track.children[0];
        const itemWidth = item.offsetWidth;
        const gap = 32; // match CSS
        return itemWidth + gap;
    }

    // Update carousel position
    function updateCarouselPosition(animate = true) {
        const itemWidth = getItemWidth();
        const offset = -itemWidth * currentIndex;

        if (animate) {
            track.style.transition = 'transform 0.5s cubic-bezier(0.4, 0, 0.2, 1)';
        } else {
            track.style.transition = 'none';
        }

        track.style.transform = `translateX(${offset}px)`;
    }

    // Handle infinite loop
    function handleInfiniteLoop() {
        isTransitioning = true;

        track.addEventListener('transitionend', function handleTransition() {
            track.removeEventListener('transitionend', handleTransition);

            // If we're at the end, jump to the start
            if (currentIndex >= itemCount * 2) {
                currentIndex = itemCount;
                updateCarouselPosition(false);
            }
            // If we're at the start, jump to the end
            else if (currentIndex < itemCount) {
                currentIndex = itemCount * 2 - 1;
                updateCarouselPosition(false);
            }

            isTransitioning = false;
            updateDots();
        });
    }

    // Create dots (only for original items)
    function createDots() {
        dotsContainer.innerHTML = '';
        for (let i = 0; i < itemCount; i++) {
            const dot = document.createElement('div');
            dot.className = 'carousel-dot';
            if (i === 0) dot.classList.add('active');
            dot.addEventListener('click', () => goToSlide(i));
            dotsContainer.appendChild(dot);
        }
    }

    // Update dots
    function updateDots() {
        const dots = dotsContainer.querySelectorAll('.carousel-dot');
        const actualIndex = ((currentIndex - itemCount) % itemCount + itemCount) % itemCount;

        dots.forEach((dot, index) => {
            dot.classList.toggle('active', index === actualIndex);
        });
    }

    // Go to specific slide
    function goToSlide(index) {
        if (isTransitioning) return;
        currentIndex = itemCount + index;
        updateCarouselPosition();
        updateDots();
    }

    // Next slide
    function nextSlide() {
        if (isTransitioning) return;
        currentIndex++;
        updateCarouselPosition();
        handleInfiniteLoop();
    }

    // Previous slide
    function prevSlide() {
        if (isTransitioning) return;
        currentIndex--;
        updateCarouselPosition();
        handleInfiniteLoop();
    }

    // Button click handlers
    nextBtn.addEventListener('click', (e) => {
        nextSlide();
        addRipple(e, nextBtn);
    });

    prevBtn.addEventListener('click', (e) => {
        prevSlide();
        addRipple(e, prevBtn);
    });

    // Keyboard navigation
    document.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowLeft') prevSlide();
        if (e.key === 'ArrowRight') nextSlide();
    });

    // Touch/drag support
    let startX = 0;
    let currentX = 0;
    let isDragging = false;
    let startIndex = 0;

    track.addEventListener('mousedown', dragStart);
    track.addEventListener('touchstart', dragStart);
    track.addEventListener('mouseup', dragEnd);
    track.addEventListener('touchend', dragEnd);
    track.addEventListener('mousemove', drag);
    track.addEventListener('touchmove', drag);
    track.addEventListener('mouseleave', dragEnd);

    function dragStart(e) {
        if (isTransitioning) return;
        isDragging = true;
        startIndex = currentIndex;
        startX = getPositionX(e);
        track.style.cursor = 'grabbing';
    }

    function drag(e) {
        if (!isDragging) return;
        e.preventDefault();

        currentX = getPositionX(e);
        const diff = currentX - startX;
        const itemWidth = getItemWidth();
        const baseOffset = -itemWidth * currentIndex;

        track.style.transition = 'none';
        track.style.transform = `translateX(${baseOffset + diff}px)`;
    }

    function dragEnd() {
        if (!isDragging) return;
        isDragging = false;
        track.style.cursor = 'grab';

        const diff = currentX - startX;
        const threshold = 50;

        if (diff > threshold) {
            prevSlide();
        } else if (diff < -threshold) {
            nextSlide();
        } else {
            updateCarouselPosition();
        }
    }

    function getPositionX(e) {
        return e.type.includes('mouse') ? e.pageX : e.touches[0].clientX;
    }

    // Ripple effect
    function addRipple(e, button) {
        const ripple = document.createElement('span');
        ripple.classList.add('ripple');

        const rect = button.getBoundingClientRect();
        const size = Math.max(rect.width, rect.height);
        const x = e.clientX - rect.left - size / 2;
        const y = e.clientY - rect.top - size / 2;

        ripple.style.width = ripple.style.height = size + 'px';
        ripple.style.left = x + 'px';
        ripple.style.top = y + 'px';

        button.appendChild(ripple);
        setTimeout(() => ripple.remove(), 600);
    }

    // Handle window resize
    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            updateCarouselPosition(false);
        }, 250);
    });

    // Initialize
    setupInfiniteCarousel();
    createDots();
    updateDots();

    // Set cursor
    track.style.cursor = 'grab';
});
