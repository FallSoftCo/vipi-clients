import { thread } from "./demo-conversation.js?v=384c497536e7";
import { initializeFishSchool } from "./fish-school.js?v=59fd8e7c7570";
import { initializeWaitlist } from "./waitlist.js?v=f71d018ae901";

function initializeConversation() {
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
}

initializeFishSchool();
initializeConversation();
initializeWaitlist();
