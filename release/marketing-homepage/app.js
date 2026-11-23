(() => {
  const thread = [
    {"id": "found-keys", "sender": "Auntie", "day": "Friday", "clock": "12:18 PM", "original": "Found some keys under our table.", "shallow": ["Found some ", "llaves", " under our table."], "deep": "Encontré unas llaves debajo de nuestra mesa."},
    {"id": "bike-keyring", "sender": "You", "day": "Friday", "clock": "12:19 PM", "original": "Little red bike on the keyring?", "shallow": ["Little red ", "bici", " on the keyring?"], "deep": "¿Hay una bici roja en el llavero?"},
    {"id": "in-my-pocket", "sender": "Auntie", "day": "Friday", "clock": "12:20 PM", "original": "Yep, the one your dad made. They’re in my pocket.", "shallow": ["Yep, the one your dad made. They’re in my ", "bolsillo", "."], "deep": "Sí, la que hizo tu papá. Las tengo en el bolsillo."},
    {"id": "coming-back", "sender": "You", "day": "Friday", "clock": "12:20 PM", "original": "I’m by the bakery. Coming back now.", "shallow": ["I’m by the ", "panadería", ". Coming back now."], "deep": "Estoy junto a la panadería. Ya vuelvo."},
    {"id": "by-the-window", "sender": "Auntie", "day": "Friday", "clock": "12:21 PM", "original": "I’ll wait by the window.", "shallow": ["I’ll wait by the ", "ventana", "."], "deep": "Te espero junto a la ventana."},
    {"id": "home-again", "sender": "You", "day": "Friday", "clock": "6:04 PM", "original": "Home. Keys are back on their hook.", "shallow": ["Home. Keys are back on their ", "gancho", "."], "deep": "Ya estoy en casa. Volví a colgar las llaves en el gancho."},
    {"id": "recognition", "sender": "Auntie", "day": "Friday", "clock": "6:05 PM", "original": "I remember your dad making those out of wire.", "shallow": ["I remember your dad making those out of ", "alambre", "."], "deep": "Me acuerdo de cómo los hacía tu papá con alambre."},
    {"id": "green-bike", "sender": "You", "day": "Friday", "clock": "6:07 PM", "original": "I sent him a photo. He asked about your green bike.", "shallow": ["I sent him a ", "foto", ". He asked about your green bike."], "deep": "Le mandé una foto. Me preguntó por tu bici verde."},
    {"id": "squeaky-brakes", "sender": "Auntie", "day": "Friday", "clock": "6:08 PM", "original": "Still gets me to work. You can hear the brakes a block away.", "shallow": ["Still gets me to work. You can hear the ", "frenos", " a block away."], "deep": "Todavía voy al trabajo en ella. Los frenos se oyen a una cuadra."},
    {"id": "saturday-repair", "sender": "You", "day": "Friday", "clock": "6:09 PM", "original": "He says he can take a look on Saturday.", "shallow": ["He says he can take a look on ", "sábado", "."], "deep": "Dice que el sábado le puede echar un vistazo."},
    {"id": "old-shop", "sender": "Auntie", "day": "Friday", "clock": "6:10 PM", "original": "Is his shop still behind the bakery?", "shallow": ["Is his ", "taller", " still behind the bakery?"], "deep": "¿Su taller sigue detrás de la panadería?"},
    {"id": "garage", "sender": "You", "day": "Friday", "clock": "6:11 PM", "original": "He works in our garage now.", "shallow": ["He works in our ", "garaje", " now."], "deep": "Ahora trabaja en nuestro garaje."},
    {"id": "what-time", "sender": "Auntie", "day": "Friday", "clock": "6:12 PM", "original": "What time should I come by?", "shallow": ["What ", "hora", " should I come by?"], "deep": "¿A qué hora paso?"},
    {"id": "side-door", "sender": "You", "day": "Friday", "clock": "6:13 PM", "original": "Ten works. Use the side door.", "shallow": ["Ten works. Use the side ", "puerta", "."], "deep": "A las diez está bien. Entra por la puerta lateral."},
    {"id": "cinnamon-rolls", "sender": "Auntie", "day": "Friday", "clock": "6:14 PM", "original": "I’ll bring those cinnamon rolls he likes.", "shallow": ["I’ll bring those ", "canela", " rolls he likes."], "deep": "Llevo esos rollos de canela que le gustan."},
    {"id": "middle-roll", "sender": "You", "day": "Friday", "clock": "6:15 PM", "original": "Save me the middle one. It gets all the icing.", "shallow": ["Save me the middle one. It gets all the ", "glaseado", "."], "deep": "Guárdame el del medio. Es el que lleva más glaseado."},
    {"id": "tray", "sender": "Auntie", "day": "Friday", "clock": "6:16 PM", "original": "I remember. You used to scrape the tray.", "shallow": ["I remember. You used to scrape the ", "bandeja", "."], "deep": "Me acuerdo. Antes raspabas la bandeja."},
    {"id": "sold-out", "sender": "Auntie", "day": "Saturday", "clock": "9:43 AM", "original": "The bakery is out of cinnamon rolls.", "shallow": ["The ", "panadería", " is out of cinnamon rolls."], "deep": "En la panadería ya no quedan rollos de canela."},
    {"id": "bread", "sender": "You", "day": "Saturday", "clock": "9:44 AM", "original": "Dad would love some bread. He’s already made coffee.", "shallow": ["Dad would love some ", "pan", ". He’s already made coffee."], "deep": "A mi papá le encantaría un poco de pan. Ya hizo café."},
    {"id": "warm-loaf", "sender": "Auntie", "day": "Saturday", "clock": "9:45 AM", "original": "They’ve got a warm loaf. I’ll take it.", "shallow": ["They’ve got a warm ", "hogaza", ". I’ll take it."], "deep": "Tienen una hogaza calentita. Me la llevo."},
    {"id": "corner", "sender": "You", "day": "Saturday", "clock": "9:48 AM", "original": "Want me to meet you at the corner?", "shallow": ["Want me to meet you at the ", "esquina", "?"], "deep": "¿Quieres que te espere en la esquina?"},
    {"id": "blue-gate", "sender": "Auntie", "day": "Saturday", "clock": "9:49 AM", "original": "I remember the blue gate.", "shallow": ["I remember the blue ", "portón", "."], "deep": "Me acuerdo del portón azul."},
    {"id": "repainted", "sender": "You", "day": "Saturday", "clock": "9:50 AM", "original": "It’s green now. Dad finally painted it.", "shallow": ["It’s ", "verde", " now. Dad finally painted it."], "deep": "Ahora es verde. Mi papá por fin lo pintó."},
    {"id": "wrong-bell", "sender": "Auntie", "day": "Saturday", "clock": "9:54 AM", "original": "Good thing you said that. I nearly rang the wrong bell.", "shallow": ["Good thing you said that. I nearly rang the wrong ", "timbre", "."], "deep": "Menos mal que me avisaste. Casi toco el timbre equivocado."},
    {"id": "mugs", "sender": "You", "day": "Saturday", "clock": "9:55 AM", "original": "I’m outside with two mugs.", "shallow": ["I’m outside with two ", "tazas", "."], "deep": "Estoy afuera con dos tazas."},
    {"id": "ride-home", "sender": "You", "day": "Saturday", "clock": "12:16 PM", "original": "How are the brakes on the ride home?", "shallow": ["How are the ", "frenos", " on the ride home?"], "deep": "¿Qué tal van los frenos de camino a casa?"},
    {"id": "birds", "sender": "Auntie", "day": "Saturday", "clock": "12:24 PM", "original": "Quiet. I can actually hear the birds now.", "shallow": ["Quiet. I can actually hear the ", "pájaros", " now."], "deep": "Ya no hacen ruido. Ahora hasta oigo los pájaros."},
    {"id": "test-hill", "sender": "You", "day": "Saturday", "clock": "12:25 PM", "original": "Dad wants to know if you tried the hill by the park.", "shallow": ["Dad wants to know if you tried the ", "cuesta", " by the park."], "deep": "Mi papá pregunta si probaste la cuesta que hay junto al parque."},
    {"id": "crossing", "sender": "Auntie", "day": "Saturday", "clock": "12:26 PM", "original": "Just did. Stopped right at the crossing.", "shallow": ["Just did. Stopped right at the ", "cruce", "."], "deep": "La acabo de probar. Frené justo en el cruce."},
    {"id": "repair-report", "sender": "You", "day": "Saturday", "clock": "12:28 PM", "original": "I read him your message. He’s smiling.", "shallow": ["I read him your ", "mensaje", ". He’s smiling."], "deep": "Le leí tu mensaje. Está sonriendo."},
    {"id": "plum-jam", "sender": "Auntie", "day": "Saturday", "clock": "12:31 PM", "original": "Who made the plum jam we had with the bread?", "shallow": ["Who made the plum ", "mermelada", " we had with the bread?"], "deep": "¿Quién hizo la mermelada de ciruela que comimos con el pan?"},
    {"id": "envelope", "sender": "You", "day": "Saturday", "clock": "12:32 PM", "original": "Dad did. His recipe’s on the back of an envelope.", "shallow": ["Dad did. His recipe’s on the back of an ", "sobre", "."], "deep": "Mi papá. Tiene la receta escrita en el dorso de un sobre."},
    {"id": "recipe-photo", "sender": "Auntie", "day": "Saturday", "clock": "12:33 PM", "original": "Could you take a picture of it for me?", "shallow": ["Could you take a ", "foto", " of it for me?"], "deep": "¿Me mandas una foto?"},
    {"id": "ingredients", "sender": "You", "day": "Saturday", "clock": "12:35 PM", "original": "It just says plums, sugar, lemon.", "shallow": ["It just says plums, ", "azúcar", ", lemon."], "deep": "Solo dice ciruelas, azúcar y limón."},
    {"id": "amounts", "sender": "Auntie", "day": "Saturday", "clock": "12:36 PM", "original": "No amounts? That sounds like him.", "shallow": ["No ", "cantidades", "? That sounds like him."], "deep": "¿Sin cantidades? Muy típico de él."},
    {"id": "batch", "sender": "You", "day": "Saturday", "clock": "12:38 PM", "original": "I’ll make a batch with him tomorrow and weigh everything.", "shallow": ["I’ll make a ", "tanda", " with him tomorrow and weigh everything."], "deep": "Mañana hago una tanda con él y lo peso todo."},
    {"id": "two-kilos", "sender": "You", "day": "Sunday", "clock": "10:06 AM", "original": "Two kilos of plums. That’s what we started with.", "shallow": ["Two kilos of ", "ciruelas", ". That’s what we started with."], "deep": "Empezamos con dos kilos de ciruelas."},
    {"id": "noted", "sender": "Auntie", "day": "Sunday", "clock": "10:08 AM", "original": "Got it. How much sugar?", "shallow": ["Got it. How much ", "azúcar", "?"], "deep": "Anotado. ¿Cuánto azúcar?"},
    {"id": "one-lemon", "sender": "You", "day": "Sunday", "clock": "10:09 AM", "original": "A kilo. Plus the juice of one lemon.", "shallow": ["A kilo. Plus the juice of one ", "limón", "."], "deep": "Un kilo. Y el jugo de un limón."},
    {"id": "skin", "sender": "Auntie", "day": "Sunday", "clock": "10:10 AM", "original": "Does he leave the skin on?", "shallow": ["Does he leave the ", "piel", " on?"], "deep": "¿Les deja la piel?"},
    {"id": "purple", "sender": "You", "day": "Sunday", "clock": "10:11 AM", "original": "Yep. The jam turns purple as it cooks.", "shallow": ["Yep. The jam turns ", "morada", " as it cooks."], "deep": "Sí. La mermelada se pone morada al cocinarse."},
    {"id": "doneness", "sender": "Auntie", "day": "Sunday", "clock": "10:13 AM", "original": "How do you know when it’s ready?", "shallow": ["How do you know when it’s ", "lista", "?"], "deep": "¿Cómo sabes cuándo está lista?"},
    {"id": "cold-plate", "sender": "You", "day": "Sunday", "clock": "10:42 AM", "original": "He puts a spoonful on a cold plate.", "shallow": ["He puts a spoonful on a cold ", "plato", "."], "deep": "Pone una cucharada en un plato frío."},
    {"id": "wrinkle", "sender": "You", "day": "Sunday", "clock": "10:43 AM", "original": "Push it with your finger. Look for a wrinkle.", "shallow": ["Push it with your finger. Look for a ", "arruga", "."], "deep": "Empújala con el dedo. Fíjate si se forma una arruga."},
    {"id": "missing-step", "sender": "Auntie", "day": "Sunday", "clock": "10:45 AM", "original": "That part wasn’t on the envelope.", "shallow": ["That part wasn’t on the ", "sobre", "."], "deep": "Esa parte no estaba en el sobre."},
    {"id": "recipe-card", "sender": "You", "day": "Sunday", "clock": "10:46 AM", "original": "I wrote it all on a card this time.", "shallow": ["I wrote it all on a ", "tarjeta", " this time."], "deep": "Esta vez lo anoté todo en una tarjeta."},
    {"id": "market", "sender": "Auntie", "day": "Sunday", "clock": "4:20 PM", "original": "I’m at the market. Guess what’s on sale.", "shallow": ["I’m at the ", "mercado", ". Guess what’s on sale."], "deep": "Estoy en el mercado. Adivina qué está de oferta."},
    {"id": "empty-jars", "sender": "You", "day": "Sunday", "clock": "4:22 PM", "original": "Plums? I’ve got empty jars if you need them.", "shallow": ["Plums? I’ve got empty ", "frascos", " if you need them."], "deep": "¿Ciruelas? Tengo frascos vacíos por si los necesitas."},
    {"id": "enough-fruit", "sender": "Auntie", "day": "Sunday", "clock": "4:23 PM", "original": "Please. I bought enough fruit to share.", "shallow": ["Please. I bought enough ", "fruta", " to share."], "deep": "Sí, por favor. Compré suficiente fruta para compartir contigo."},
    {"id": "recipe-return", "sender": "You", "day": "Sunday", "clock": "4:25 PM", "original": "I’ll drop them off tonight, with the recipe.", "shallow": ["I’ll drop them off tonight, with the ", "receta", "."], "deep": "Te los llevo esta noche, con la receta."}
  ];
  const byId = id => document.getElementById(id);
  const panel = byId('conversation'), history = byId('history'), art = byId('friend-scene');
  const modePill = byId('mode-toggle');
  const hand = modePill.querySelector('.gesture');
  const speaker = art.querySelector('.voice-symbol');
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
  soundHint.append(speaker.cloneNode(true), 'Tap');
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
    submit.textContent = 'Joining…';
    email.readOnly = true;
    status.textContent = 'Joining the launch list…';

    try {
      const response = await fetch('/api/waitlist', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
        body: JSON.stringify(payload),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.ok) {
        throw new SubmissionError(result.error || 'The launch list is temporarily unavailable. Please try again.');
      }
      status.dataset.state = 'success';
      status.textContent = 'You’re on the list. We’ll email you when Vipi is ready.';
      submit.textContent = 'You’re on the list';
      consent.disabled = true;
      record('waitlist_submit_success');
    } catch (error) {
      status.dataset.state = 'error';
      status.textContent = error instanceof SubmissionError
        ? error.message : 'We couldn’t reach the launch list. Check your connection and try again.';
      submit.disabled = false;
      submit.textContent = originalLabel;
      email.readOnly = false;
      record('waitlist_submit_error');
    }
  });
})();
