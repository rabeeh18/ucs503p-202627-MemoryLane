<!-- Loading placeholder: a few topic ovals pulsing slowly (static with reduced motion). -->
<div class="skeleton" aria-busy="true" aria-label="Loading your map">
  <svg viewBox="0 0 1400 900" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
    <ellipse cx="420" cy="300" rx="210" ry="150" />
    <ellipse cx="900" cy="250" rx="170" ry="125" style="animation-delay: 0.3s" />
    <ellipse cx="380" cy="660" rx="150" ry="105" style="animation-delay: 0.6s" />
    <ellipse cx="890" cy="650" rx="170" ry="110" style="animation-delay: 0.9s" />
  </svg>
</div>

<style>
  .skeleton {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  svg {
    width: 100%;
    height: 100%;
  }

  ellipse {
    fill: var(--map-topic);
    stroke: var(--map-topic-border);
    stroke-width: 1;
    animation: pulse 2.4s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 0.45; }
    50% { opacity: 1; }
  }

  @media (prefers-reduced-motion: reduce) {
    ellipse {
      animation: none;
      opacity: 0.7;
    }
  }
</style>
