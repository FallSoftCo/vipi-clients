export function initializeFishSchool() {
  const school = document.getElementById('fish-school');
  if (!school) return;

  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const fishSource = school.dataset.fishSrc || '/assets/mackerel.svg';
  const cycleLength = 92;
  const passWindows = [
    { start: 0, duration: 15, width: 0.54, lane: 0.55, heading: 1 },
    { start: 3.2, duration: 13, width: 0.34, lane: 0.34, heading: -1 },
    { start: 25.5, duration: 11, width: 0.31, lane: 0.71 },
    { start: 39, duration: 14, width: 0.31, lane: 0.42 },
    { start: 53.5, duration: 10, width: 0.31, lane: 0.63 },
    { start: 70, duration: 13, width: 0.31, lane: 0.32 },
    { start: 78.5, duration: 10, width: 0.31, lane: 0.73 },
  ];
  const fish = passWindows.map(() => {
    const image = document.createElement('img');
    image.src = fishSource;
    image.alt = '';
    image.draggable = false;
    image.decoding = 'async';
    school.append(image);
    return image;
  });
  let elapsed = 7.2;
  let lastFrame = 0;
  let lastPaint = 0;
  let animationFrame = 0;
  let running = false;
  let passes = [];
  let passCycle = -1;

  function randomFor(cycle) {
    let state = (0x4d41434b ^ Math.imul(cycle + 1, 0xd1342543)) >>> 0;
    return () => {
      state = (state + 0x9e3779b9) >>> 0;
      let value = state;
      value = Math.imul(value ^ (value >>> 15), value | 1);
      value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
      return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
    };
  }

  function schoolFor(cycle) {
    if (cycle === passCycle) return passes;
    const random = randomFor(cycle);
    const firstHeading = random() < 0.5 ? -1 : 1;
    passes = passWindows.map((window, index) => {
      const heading =
        index === 0 ? firstHeading : index === 1 ? -firstHeading : random() < 0.5 ? -1 : 1;
      return {
        start: window.start + (index === 0 ? 0 : random()),
        duration: window.duration + random() * (index === passWindows.length - 1 ? 2 : 4),
        width: window.width + random() * (index < 2 ? 0.1 : 0.34),
        lane: window.lane + (random() - 0.5) * 0.08,
        amplitude: 0.014 + random() * 0.018,
        arc: random() * Math.PI * 2,
        heading,
      };
    });
    passCycle = cycle;
    return passes;
  }

  function setFish(image, width, x, y, angle, heading, opacity) {
    image.style.width = width.toFixed(2) + 'px';
    image.style.transform =
      'translate3d(' +
      x.toFixed(2) +
      'px,' +
      y.toFixed(2) +
      'px,0) rotate(' +
      angle.toFixed(3) +
      'deg) scaleX(' +
      heading +
      ')';
    image.style.opacity = opacity.toFixed(3);
  }

  function drawSchool() {
    const viewportWidth = document.documentElement.clientWidth;
    const viewportHeight = window.innerHeight;
    const cycle = Math.floor(elapsed / cycleLength);
    const time = elapsed % cycleLength;
    const opacityBase = viewportWidth < 700 ? 0.19 : 0.24;
    schoolFor(cycle).forEach((pass, index) => {
      const image = fish[index];
      const progress = (time - pass.start) / pass.duration;
      if (progress < 0 || progress > 1) {
        image.style.opacity = '0';
        return;
      }
      const width = Math.min(viewportWidth * pass.width, 350);
      const height = (width * 170) / 640;
      const travel = viewportWidth + width + 16;
      const center = viewportWidth / 2 + pass.heading * (progress - 0.5) * travel;
      const arc = pass.arc + progress * Math.PI * 1.5;
      const y = viewportHeight * (pass.lane + pass.amplitude * Math.sin(arc)) - height / 2;
      const slope = (viewportHeight * pass.amplitude * Math.PI * 1.5 * Math.cos(arc)) / travel;
      const angle = Math.max(-4, Math.min(4, (Math.atan(slope) * 180) / Math.PI));
      const opacity = opacityBase * (0.51 + (0.49 * (pass.width - 0.31)) / 0.34);
      setFish(image, width, center - width / 2, y, angle, pass.heading, opacity);
    });
  }

  function drawStillSchool() {
    const viewportWidth = document.documentElement.clientWidth;
    const viewportHeight = window.innerHeight;
    const poses = [
      { width: Math.min(viewportWidth * 0.38, 150), lane: 0.29, heading: 1, angle: -2 },
      { width: Math.min(viewportWidth * 0.28, 112), lane: 0.61, heading: -1, angle: 2 },
      { width: Math.min(viewportWidth * 0.21, 86), lane: 0.76, heading: 1, angle: -1 },
    ];
    fish.forEach((image, index) => {
      const pose = poses[index];
      if (!pose) {
        image.style.opacity = '0';
        return;
      }
      const height = (pose.width * 170) / 640;
      const x = viewportWidth * (index === 0 ? 0.12 : index === 1 ? 0.58 : 0.38);
      setFish(
        image,
        pose.width,
        x,
        viewportHeight * pose.lane - height / 2,
        pose.angle,
        pose.heading,
        0.14,
      );
    });
  }

  function tick(now) {
    if (!running) return;
    if (lastFrame) elapsed += Math.min(0.1, (now - lastFrame) / 1000);
    lastFrame = now;
    if (!lastPaint || now - lastPaint >= 1000 / 24) {
      drawSchool();
      lastPaint = now;
    }
    animationFrame = requestAnimationFrame(tick);
  }

  function updateMotion() {
    const active = !document.hidden && !reducedMotion.matches;
    if (active === running) return;
    running = active;
    if (active) {
      lastFrame = 0;
      animationFrame = requestAnimationFrame(tick);
    } else {
      cancelAnimationFrame(animationFrame);
      animationFrame = 0;
      if (reducedMotion.matches) drawStillSchool();
    }
  }

  if (reducedMotion.matches) drawStillSchool();
  else drawSchool();
  updateMotion();
  reducedMotion.addEventListener('change', updateMotion);
  document.addEventListener('visibilitychange', updateMotion);
  window.addEventListener('resize', () => {
    if (!running) drawStillSchool();
    else drawSchool();
  });
}
