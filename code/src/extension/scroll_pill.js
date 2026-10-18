// Floating scroll indicator for extension pages (same behaviour as the web
// app's ScrollPill.svelte). Native scrollbars are hidden in tokens.css; native
// wheel, touch and keyboard scrolling are untouched. The pill only appears
// when the page overflows.
const MIN_HEIGHT = 32;
const EDGE = 6;
const HOT_ZONE = 24;
const HIDE_AFTER_MS = 1000;

export function installScrollPill() {
    const scroller = () => document.scrollingElement || document.documentElement;
    const pill = document.createElement("div");
    pill.className = "scroll-pill";
    pill.setAttribute("aria-hidden", "true");
    document.body.append(pill);

    let overflow = false;
    let height = MIN_HEIGHT;
    let hovering = false;
    let dragging = false;
    let visible = false;
    let hideTimer = 0;
    let frame = 0;
    let dragStartY = 0;
    let dragStartScroll = 0;

    function paint() {
        pill.hidden = !overflow;
        pill.classList.toggle("visible", visible || hovering || dragging);
        pill.classList.toggle("active", hovering || dragging);
    }

    function measure() {
        frame = 0;
        const el = scroller();
        const viewport = window.innerHeight;
        overflow = el.scrollHeight > viewport + 1;
        if (overflow) {
            const track = viewport - EDGE * 2;
            height = Math.max(MIN_HEIGHT, Math.round((viewport / el.scrollHeight) * track));
            const progress = Math.min(1, Math.max(0, el.scrollTop / (el.scrollHeight - viewport)));
            pill.style.height = `${height}px`;
            pill.style.transform = `translateY(${EDGE + Math.round(progress * (track - height))}px)`;
        }
        paint();
    }

    const schedule = () => { if (!frame) frame = requestAnimationFrame(measure); };

    function show() {
        visible = true;
        paint();
        clearTimeout(hideTimer);
        hideTimer = setTimeout(() => {
            visible = false;
            paint();
        }, HIDE_AFTER_MS);
    }

    window.addEventListener("scroll", () => { schedule(); show(); }, { passive: true });
    window.addEventListener("resize", schedule);
    window.addEventListener("pointermove", (event) => {
        if (overflow && !dragging && event.clientX >= window.innerWidth - HOT_ZONE) show();
    });
    pill.addEventListener("pointerenter", () => { hovering = true; show(); });
    pill.addEventListener("pointerleave", () => { hovering = false; show(); });
    pill.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        dragging = true;
        dragStartY = event.clientY;
        dragStartScroll = scroller().scrollTop;
        try { pill.setPointerCapture(event.pointerId); } catch (_err) { /* optional */ }
        paint();
    });
    pill.addEventListener("pointermove", (event) => {
        if (!dragging) return;
        const el = scroller();
        const track = window.innerHeight - EDGE * 2 - height;
        if (track > 0) {
            el.scrollTop = dragStartScroll + ((event.clientY - dragStartY) / track) * (el.scrollHeight - window.innerHeight);
        }
    });
    const endDrag = () => { dragging = false; show(); };
    pill.addEventListener("pointerup", endDrag);
    pill.addEventListener("pointercancel", endDrag);

    new ResizeObserver(schedule).observe(document.body);
    measure();
}
