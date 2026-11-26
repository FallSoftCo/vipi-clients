import { thread } from "./demo-conversation.js?v=384c497536e7";

(() => {
  const school = document.getElementById('fish-school');
  if (school) {
    const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
    const fishSource = school.dataset.fishSrc || '/assets/mackerel.svg';
    const cycleLength = 92;
    const passWindows = [
      {start: 0, duration: 15, width: .54, lane: .55, heading: 1},
      {start: 3.2, duration: 13, width: .34, lane: .34, heading: -1},
      {start: 25.5, duration: 11, width: .31, lane: .71},
      {start: 39, duration: 14, width: .31, lane: .42},
      {start: 53.5, duration: 10, width: .31, lane: .63},
      {start: 70, duration: 13, width: .31, lane: .32},
      {start: 78.5, duration: 10, width: .31, lane: .73},
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
      const firstHeading = random() < .5 ? -1 : 1;
      passes = passWindows.map((window, index) => {
        const heading = index === 0 ? firstHeading : index === 1 ? -firstHeading : random() < .5 ? -1 : 1;
        return {
          start: window.start + (index === 0 ? 0 : random()),
          duration: window.duration + random() * (index === passWindows.length - 1 ? 2 : 4),
          width: (window.width + random() * (index < 2 ? .10 : .34)),
          lane: window.lane + (random() - .5) * .08,
          amplitude: .014 + random() * .018,
          arc: random() * Math.PI * 2,
          heading,
        };
      });
      passCycle = cycle;
      return passes;
    }

    function setFish(image, width, x, y, angle, heading, opacity) {
      image.style.width = width.toFixed(2) + 'px';
      image.style.transform = 'translate3d(' + x.toFixed(2) + 'px,' + y.toFixed(2) + 'px,0) rotate(' + angle.toFixed(3) + 'deg) scaleX(' + heading + ')';
      image.style.opacity = opacity.toFixed(3);
    }

    function drawSchool() {
      const viewportWidth = document.documentElement.clientWidth;
      const viewportHeight = window.innerHeight;
      const cycle = Math.floor(elapsed / cycleLength);
      const time = elapsed % cycleLength;
      const opacityBase = viewportWidth < 700 ? .19 : .24;
      schoolFor(cycle).forEach((pass, index) => {
        const image = fish[index];
        const progress = (time - pass.start) / pass.duration;
        if (progress < 0 || progress > 1) {
          image.style.opacity = '0';
          return;
        }
        const width = Math.min(viewportWidth * pass.width, 350);
        const height = width * 170 / 640;
        const travel = viewportWidth + width + 16;
        const center = viewportWidth / 2 + pass.heading * (progress - .5) * travel;
        const arc = pass.arc + progress * Math.PI * 1.5;
        const y = viewportHeight * (pass.lane + pass.amplitude * Math.sin(arc)) - height / 2;
        const slope = viewportHeight * pass.amplitude * Math.PI * 1.5 * Math.cos(arc) / travel;
        const angle = Math.max(-4, Math.min(4, Math.atan(slope) * 180 / Math.PI));
        const opacity = opacityBase * (.51 + .49 * (pass.width - .31) / .34);
        setFish(image, width, center - width / 2, y, angle, pass.heading, opacity);
      });
    }

    function drawStillSchool() {
      const viewportWidth = document.documentElement.clientWidth;
      const viewportHeight = window.innerHeight;
      const poses = [
        {width: Math.min(viewportWidth * .38, 150), lane: .29, heading: 1, angle: -2},
        {width: Math.min(viewportWidth * .28, 112), lane: .61, heading: -1, angle: 2},
        {width: Math.min(viewportWidth * .21, 86), lane: .76, heading: 1, angle: -1},
      ];
      fish.forEach((image, index) => {
        const pose = poses[index];
        if (!pose) {
          image.style.opacity = '0';
          return;
        }
        const height = pose.width * 170 / 640;
        const x = viewportWidth * (index === 0 ? .12 : index === 1 ? .58 : .38);
        setFish(image, pose.width, x, viewportHeight * pose.lane - height / 2, pose.angle, pose.heading, .14);
      });
    }

    function tick(now) {
      if (!running) return;
      if (lastFrame) elapsed += Math.min(.1, (now - lastFrame) / 1000);
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

    if (reducedMotion.matches) drawStillSchool(); else drawSchool();
    updateMotion();
    reducedMotion.addEventListener('change', updateMotion);
    document.addEventListener('visibilitychange', updateMotion);
    window.addEventListener('resize', () => { if (!running) drawStillSchool(); else drawSchool(); });
  }

  const languageList = document.querySelector('#languages .language-list');
  if (languageList) {
    const items = [...languageList.children];
    const originalOrder = items.map(item => item.lang).join('|');
    const randomIndex = max => {
      if (!globalThis.crypto?.getRandomValues) return Math.floor(Math.random() * max);
      const value = new Uint32Array(1);
      crypto.getRandomValues(value);
      return value[0] % max;
    };
    for (let index = items.length - 1; index > 0; index -= 1) {
      const swapIndex = randomIndex(index + 1);
      [items[index], items[swapIndex]] = [items[swapIndex], items[index]];
    }
    if (items.map(item => item.lang).join('|') === originalOrder) {
      [items[0], items[1]] = [items[1], items[0]];
    }
    items.forEach(item => languageList.append(item));
    languageList.dataset.order = 'shuffled';
  }

  const byId = id => document.getElementById(id);
  const panel = byId('conversation'), history = byId('history');
  const modePill = byId('mode-toggle');
  const hand = modePill.querySelector('.gesture');
  const draftWords = byId('draft-words');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const stream = document.createElement('div');
  stream.className = 'chat-stream';
  const rows = new Map();
  for (const button of history.querySelectorAll('[data-message]')) {
    rows.set(button.dataset.message, button.closest('.screen-turn'));
  }
  stream.append(...Array.from(history.children));
  history.append(stream);

  const frames = [];
  function frame(position, phase, deep, delay, words = '') { frames.push({position, phase, deep, delay, words}); }
  for (let position = 0; position < thread.length; position++) {
    const message = thread[position], next = thread[position + 1];
    const deep = position > 2 && Math.floor(position / 4) % 2 === 1;
    frame(position, message.sender === 'You' ? 'send' : 'receive', deep, position < 3 ? 1500 : 2300);
    if (position === 2 || position > 2 && position % 7 === 2) {
      frame(position,'mode',true,1800); frame(position,'hear',true,2100);
      frame(position,'original',true,2200); frame(position,'read',true,1200);
    } else if (position % 8 === 4) frame(position,'hear',deep,1800);
    if (!next) { frame(position,'read',deep,4200); continue; }
    if (next.sender === 'Auntie') { frame(position,'typing',deep,1450); continue; }
    let typed = '';
    for (const character of next.original) {
      typed += character;
      const pause = /[,?.!]/.test(character) ? 145 : character === ' ' ? 75 : 40 + (character.codePointAt(0) % 26);
      frame(position,'compose',deep,typed === next.original ? 560 : pause,typed);
    }
  }
  let step=0, visible=false, timer=0, started=0, remaining=frames[0].delay;
  let position=2, modeDeep=false, phase='read';
  function drawText(el,message) {
    const original = (phase === 'original' && message === thread[position]);
    const face = original ? 'original' : modeDeep ? 'deep' : 'shallow';
    if (el.dataset.face === face) return;
    el.dataset.face = face;
    el.lang = face === 'deep' ? 'es' : 'en';
    if (face !== 'shallow') { el.textContent = message[face]; return; }
    const [before,word,after]=message.shallow;
    const mark=document.createElement('mark');mark.lang='es';mark.textContent=word;
    if (/^\p{L}+$/u.test(word)) mark.className='single-word';
    el.replaceChildren(before,mark,after);
  }
  function bubble(m){
    const out=m.sender==='You', row=document.createElement('div'), b=document.createElement('div');
    row.className='screen-turn '+(out?'outgoing':'incoming');row.dataset.sender=m.sender;
    b.className='native-bubble';b.dataset.message=m.id;
    const txt=document.createElement('span');txt.className='message-text';
    const stamp=document.createElement('span');stamp.className='stamp';stamp.setAttribute('aria-hidden','true');stamp.append(m.clock);
    if(out){const checks=document.createElement('span');checks.className='checks';checks.textContent='✓✓';stamp.append(checks);}
    b.append(txt,stamp);row.append(b);drawText(txt,m);return row;
  }
  const typing = document.createElement('div');
  typing.className = 'typing';
  typing.setAttribute('aria-hidden','true');
  typing.append('Auntie is typing', document.createElement('i'));
  const gesture = hand.cloneNode(true);
  const soundHint = document.createElement('span');
  soundHint.className = 'sound-hint';
  soundHint.setAttribute('aria-hidden', 'true');
  soundHint.textContent = 'Listen';
  const dates = new Map();
  const initialDate = stream.querySelector('.chat-date');
  if (initialDate) dates.set(thread[0].day, initialDate);

  function renderRows() {
    // Keep enough preceding turns to fill the clipped illustration at every supported width.
    const selected = thread.slice(Math.max(0, position - 9), position + 1);
    const keep=new Set(selected.map(message=>message.id));
    for(const [id,row] of rows) if(!keep.has(id)){row.remove();rows.delete(id);}
    const days=new Set(selected.map(message=>message.day));
    for(const [day,date] of dates) if(!days.has(day)){date.remove();dates.delete(day);}
    for(const message of selected){
      if(!dates.has(message.day)){
        const date=document.createElement('span');date.className='chat-date';date.textContent=message.day;
        dates.set(message.day,date);stream.append(date);
      }
      if(rows.has(message.id)) continue;
      const row=bubble(message);
      rows.set(message.id,row);stream.append(row);
    }
    panel.dataset.turn=String(position+1);
  }
  function draw(){
    panel.dataset.stage=phase;panel.classList.toggle('deep-view',modeDeep);
    byId('mode-name').textContent=modeDeep?'Deep':'Shallow';
    for (const message of thread.slice(Math.max(0, position - 9), position + 1)) {
      drawText(rows.get(message.id).querySelector('.message-text'), message);
    }
  }
  let modeTransition = null;
  function finishModeTransition() {
    if (!modeTransition) return;
    const {animations, ghosts, buttons} = modeTransition;
    modeTransition = null;
    for (const animation of animations) animation.cancel();
    for (const ghost of ghosts) ghost.remove();
    for (const button of buttons) button.classList.remove('changing-face');
  }

  function measureFace(el) {
    const button = el.closest('.native-bubble');
    return {width:button.offsetWidth, height:button.offsetHeight,
      x:el.offsetLeft, y:el.offsetTop, textWidth:el.offsetWidth};
  }

  function drawModeChange() {
    finishModeTransition();
    const phrases = [...history.querySelectorAll('.message-text')];
    if (!phrases.length || !phrases[0].animate || reduced.matches) {draw();return;}
    const viewport = history.getBoundingClientRect();
    const previous = phrases.map(el => {
      const bounds = el.getBoundingClientRect();
      const onscreen = (bounds.bottom >= viewport.top - 64 && bounds.top <= viewport.bottom + 64);
      return {el, old:measureFace(el), face:el.dataset.face, copy:onscreen ? el.cloneNode(true) : null};
    });
    draw();
    const next = previous.map(({el}) => measureFace(el));
    const state = {animations:[], ghosts:[], buttons:[], };
    modeTransition = state;
    const timing = {duration:340, easing:'cubic-bezier(.28,.04,.22,1)', fill:'both'};
    function animate(el, frames) { state.animations.push(el.animate(frames, timing)); }
    for (const [i,{el,old,face,copy}] of previous.entries()) {
      if (face === el.dataset.face) continue;
      const end = next[i], button = el.closest('.native-bubble');
      button.classList.add('changing-face');
      state.buttons.push(button);
      const size = metrics => ({width:metrics.width+'px',height:metrics.height+'px'});
      animate(button, [size(old), size(end)]);
      if (!copy) continue;
      // Keep each wrapped phrase intact. Only one complete face paints at any instant.
      copy.classList.add('departing-face');
      copy.setAttribute('aria-hidden', 'true');
      copy.removeAttribute('id');
      button.append(copy);
      state.ghosts.push(copy);
      const handoff = .4;
      // Both tracks switch at the same offset. The visible side retains reading contrast.
      function faceTrack(firstFace, box) {
        function at(fraction, firstVisible, offset) {
          const distance = firstFace ? fraction/handoff : (1-fraction)/(1-handoff);
          const nearSwitch = Math.min(1, Math.max(0,distance));
          const visible = firstFace === firstVisible;
          return {...box,offset,opacity:visible ? 1-.22*nearSwitch : 0,
            transform:'translateY('+((firstFace ? -1 : 1)*nearSwitch*2)+'px)'};
        }
        return [at(0,true,0), at(handoff,true,handoff), at(handoff,false,handoff), at(1,false,1)];
      }
      animate(copy, faceTrack(true,{left:old.x+'px',top:old.y+'px',width:old.textWidth+'px'}));
      animate(el, faceTrack(false,{width:end.textWidth+'px'}));
    }
    Promise.allSettled(state.animations.map(animation => animation.finished)).then(() => {
      if (modeTransition === state) finishModeTransition();
    });
  }
  function snapshot() {
    const top=history.getBoundingClientRect().top;
    return new Map([...stream.children].filter(el=>el.getBoundingClientRect().bottom>=top)
      .map(el=>[el,el.getBoundingClientRect().top]));
  }
  function settle(before,arrival) {
    for(const [el,y] of before) {
      if(!el.isConnected)continue;
      const delta=y-el.getBoundingClientRect().top;
      if(Math.abs(delta)>1 && el.animate)el.animate([{transform:'translateY('+delta+'px)'},{transform:'translateY(0)'}],
        {duration:370,easing:'cubic-bezier(.2,.72,.25,1)'});
    }
    if(arrival && arrival.animate)arrival.animate([{transform:'translateY(12px) scale(.985)'},{transform:'none'}],
      {duration:320,easing:'cubic-bezier(.18,.8,.23,1)'});
  }
  function clearCues(){
    typing.remove();gesture.remove();soundHint.remove();
    draftWords.textContent='Message';
    const pending=stream.querySelector('.checks[data-pending]');
    if(pending){pending.textContent='✓✓';delete pending.dataset.pending;}
  }
  function displayFrame(){
    const next=frames[step], changed=position!==next.position, wasPhase=phase;
    const changesMode = next.deep !== modeDeep;
    if(next.phase==='compose' && wasPhase==='compose' && !changed){
      draftWords.textContent=next.words;
      return;
    }
    const before=snapshot();
    position=next.position;modeDeep=next.deep;phase=next.phase;
    clearCues();
    if(changed)renderRows();
    if(changesMode) drawModeChange(); else draw();
    const row=rows.get(thread[position].id), target=row.querySelector('.native-bubble');
    if(phase==='typing')stream.append(typing);
    if(phase==='compose'){draftWords.textContent=next.words;}
    if(phase==='send'){
      const check=target.querySelector('.checks');
      if(check){check.textContent='✓';check.dataset.pending='true';}
    }
    if(phase==='original')target.append(gesture);
    if(phase==='hear')row.append(soundHint);
    if(changed || phase==='typing' || wasPhase==='typing' || phase==='mode' || phase==='original' || wasPhase==='original') {
      if(!changesMode) settle(before,changed?row:phase==='typing'?typing:null);
    }
  }
  function cancelTick(){
    if(!timer)return;
    clearTimeout(timer);remaining=Math.max(10,remaining-(performance.now()-started));timer=0;
  }
  function schedule(){
    const active=visible&&!document.hidden&&!reduced.matches;
    panel.classList.toggle('running',active);
    if(!active){cancelTick();return;}
    if(timer)return;
    started=performance.now();
    timer=setTimeout(()=>{timer=0;step=(step+1)%frames.length;remaining=frames[step].delay;displayFrame();schedule();},remaining);
  }

  function reset() {
    cancelTick();
    finishModeTransition();
    clearCues();
    step=0;
    remaining=frames[0].delay;
    position=reduced.matches ? 2 : 0;
    phase='read';
    modeDeep=false;
    renderRows();
    panel.classList.toggle('enhanced', !reduced.matches);
    if (reduced.matches) draw(); else displayFrame();
    schedule();
  }
  if ('IntersectionObserver' in window) {
    reset();
    new IntersectionObserver(([entry]) => {
      visible=entry.isIntersecting;
      schedule();
    }).observe(panel);
    reduced.addEventListener('change',reset);
    document.addEventListener('visibilitychange',schedule);
    window.addEventListener('pagehide',cancelTick);
    window.addEventListener('pageshow',schedule);
  }
})();

(() => {
  const form = document.getElementById('waitlist-form');
  if (!form) return;
  const status = document.getElementById('waitlist-status');
  const email = document.getElementById('waitlist-email');
  const consent = document.getElementById('waitlist-consent');
  const submit = form.querySelector('button[type="submit"]');
  if (!status || !email || !consent || !submit) return;

  const fields = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'];
  const campaignKey = 'vipi-first-touch-campaign-v1';
  const visitorKey = 'vipi-visitor-id-v1';
  class SubmissionError extends Error {}

  function readSession(key) {
    try { return sessionStorage.getItem(key); } catch (_) { return null; }
  }

  function writeSession(key, value) {
    try { sessionStorage.setItem(key, value); } catch (_) { /* Storage can be unavailable. */ }
  }

  function currentCampaign() {
    const params = new URLSearchParams(location.search);
    const incoming = {};
    for (const field of fields) {
      const value = params.get(field);
      if (value) incoming[field] = value.slice(0, 120);
    }
    if (Object.keys(incoming).length) {
      const firstTouch = {...incoming, landing_path: location.pathname,
        referrer: document.referrer || '', captured_at: new Date().toISOString()};
      writeSession(campaignKey, JSON.stringify(firstTouch));
      return firstTouch;
    }
    try {
      const saved = JSON.parse(readSession(campaignKey) || 'null');
      if (saved && typeof saved === 'object') return saved;
    } catch (_) { /* Fall through to an unattributed visit. */ }
    return {landing_path: location.pathname, referrer: document.referrer || ''};
  }

  function visitorId() {
    let id = readSession(visitorKey);
    if (id) return id;
    if (crypto.randomUUID) id = crypto.randomUUID();
    else {
      const bytes = crypto.getRandomValues(new Uint8Array(16));
      id = [...bytes].map(value => value.toString(16).padStart(2, '0')).join('');
    }
    writeSession(visitorKey, id);
    return id;
  }

  const campaign = currentCampaign();
  const visitor = visitorId();
  for (const field of fields) {
    const input = form.elements.namedItem(field);
    if (input) input.value = campaign[field] || '';
  }
  const landingPath = form.elements.namedItem('landing_path');
  const referrer = form.elements.namedItem('referrer');
  if (landingPath) landingPath.value = campaign.landing_path || location.pathname;
  if (referrer) referrer.value = campaign.referrer || document.referrer || '';

  function record(event) {
    const body = {event, visitor_id: visitor, path: location.pathname,
      referrer: campaign.referrer || '', };
    for (const field of fields) body[field] = campaign[field] || '';
    fetch('/api/marketing/event', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
      body: JSON.stringify(body),
      keepalive: true,
    }).catch(() => {});
  }

  record('page_view');
  document.addEventListener('click', event => {
    const link = event.target.closest && event.target.closest('a[href="#waitlist"]');
    if (link) record('waitlist_click');
  });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    status.textContent = '';
    status.removeAttribute('data-state');
    if (!form.reportValidity()) return;

    const payload = {};
    for (const [name, value] of new FormData(form)) payload[name] = value;
    payload.email = payload.email || email.value.trim();
    payload.consent = consent.checked ? 'yes' : '';
    payload.landing_path = campaign.landing_path || location.pathname;
    payload.referrer = campaign.referrer || document.referrer || '';
    for (const field of fields) payload[field] = campaign[field] || '';

    const originalLabel = submit.textContent;
    submit.disabled = true;
    submit.textContent = 'Saving…';
    email.readOnly = true;
    status.textContent = 'Saving your email…';

    try {
      const response = await fetch('/api/waitlist', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
        body: JSON.stringify(payload),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.ok) {
        throw new SubmissionError(result.error || 'Email signup is temporarily unavailable. Try again.');
      }
      status.dataset.state = 'success';
      status.textContent = 'You’re in. We’ll email you when Vipi opens on iPhone and Android.';
      submit.textContent = 'You’re in';
      consent.disabled = true;
      record('waitlist_submit_success');
    } catch (error) {
      status.dataset.state = 'error';
      status.textContent = error instanceof SubmissionError
        ? error.message : 'Couldn’t save your email. Check your connection and try again.';
      submit.disabled = false;
      submit.textContent = originalLabel;
      email.readOnly = false;
      record('waitlist_submit_error');
    }
  });
})();
