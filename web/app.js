'use strict';
const $=id=>document.getElementById(id), names=['你','赤松','青竹'];
const ranks={11:'J',12:'Q',13:'K',14:'A',15:'2',16:'小王',17:'大王'};
const rank=c=>c<52?Math.floor(c/4)+3:c-36;
const textRank=r=>ranks[r]||String(r);
let game=null, id=sessionStorage.getItem('ddz-table'), busy=false, stopped=false, selected=new Set();
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function notify(message='',error=false){$('notice').textContent=message;$('notice').classList.toggle('error',error);}
function mini(r,back=false){const el=document.createElement('span');el.className='mini-card'+(back?' back':'')+(r===17?' red':'');el.textContent=back?'♠':textRank(r);return el;}
function cardsInto(node,rs,back=false){node.replaceChildren(...rs.map(r=>mini(r,back)));}
function role(seat){return game.landlord===null?'待定身份':seat===game.landlord?'地主':'农民';}
function render(){
 if(!game)return;
 $('round').textContent=`第 ${game.round} 局`;
 $('phase').textContent=({bid:'叫分定地主',play:'牌局进行中',over:'本局已结束'})[game.phase];
 $('turn').textContent=game.phase==='over'?game.message:`${names[game.turn]}${game.phase==='bid'?'叫分':'出牌'}${game.turn!==0?' · AI 思考中':''}`;
 for(let s=0;s<3;s++){$('role'+s).textContent=role(s);$('role'+s).classList.toggle('landlord',s===game.landlord);$('count'+s).textContent=game.counts[s]+(s===0?' 张':'');$('score'+s).textContent=`${game.scores[s]>0?'+':''}${game.scores[s]} 分`;$('player'+s).classList.toggle('active',game.turn===s&&game.phase!=='over');}
 for(let s=1;s<3;s++){
  const bid=game.bids.find(b=>b[0]===s), last=[...game.history].reverse().find(h=>h[0]===s);
  $('status'+s).textContent=game.phase==='bid'?(bid?(bid[1]?`叫 ${bid[1]} 分`:'不叫'):'等待叫分'):game.phase==='over'?'本局结束':game.turn===s?'正在思考':last?last[1].length?'已出牌':'不出':'等待出牌';
 }
 cardsInto($('bottom'),game.phase==='bid'?[0,0,0]:game.bottom.map(rank),game.phase==='bid');
 $('bidHistory').textContent=game.bids.map(([s,b])=>`${names[s]} ${b?b+'分':'不叫'}`).join(' · ');
 cardsInto($('trick'),game.target);
 $('tableMessage').textContent=game.phase==='play'?(game.target.length?`${names[game.leader]}的上一手 · ${game.target.map(textRank).join(' ')}`:'新一轮领出 · 可以出任意合法牌型'):game.message;
 selected=new Set([...selected].filter(c=>game.hand.includes(c)));
 $('hand').replaceChildren();
 [...game.hand].sort((a,b)=>rank(b)-rank(a)||a-b).forEach(card=>{
  const r=rank(card),suit=card<52?['♠','♥','♣','♦'][card%4]:'✦';
  const b=document.createElement('button');b.type='button';b.className='card'+((card<52&&(card%4===1||card%4===3))||r===17?' red':'')+(r>=16?' joker':'')+(selected.has(card)?' selected':'');
  b.setAttribute('aria-label',`${card<52?suit:''}${textRank(r)}`);b.setAttribute('aria-pressed',String(selected.has(card)));b.disabled=busy||game.phase!=='play'||game.turn!==0;
  const number=document.createElement('span');number.textContent=textRank(r);const icon=document.createElement('span');icon.className='suit';icon.textContent=suit;const large=document.createElement('span');large.className='big-suit';large.textContent=suit;b.append(number,icon,large);
  b.addEventListener('click',()=>{selected.has(card)?selected.delete(card):selected.add(card);b.classList.toggle('selected',selected.has(card));b.setAttribute('aria-pressed',String(selected.has(card)));selection();});$('hand').append(b);
 });
 $('bidActions').hidden=game.phase!=='bid';$('playActions').hidden=game.phase!=='play';$('nextRound').hidden=game.phase!=='over';
 document.querySelectorAll('[data-bid]').forEach(b=>b.disabled=busy||game.turn!==0||(+b.dataset.bid>0&&+b.dataset.bid<=game.high_bid));
 for(const name of ['hint','clear','pass'])$(name).disabled=busy||game.turn!==0;
 $('pass').disabled ||=!game.target.length;
 $('newRound').disabled=busy;$('nextRound').disabled=busy;
 selection();
 $('result').hidden=game.phase!=='over';
 if(game.settlement){const st=game.settlement;$('result').replaceChildren();const title=document.createElement('strong');title.textContent=st.landlord_won?'地主胜出':'农民共同获胜';const detail=document.createElement('p');detail.textContent=`底分 ${st.bid} × ${st.multiplier} 倍 · ${st.bombs} 次炸弹${st.spring?' · '+st.spring:''}　${st.delta.map((n,s)=>`${names[s]} ${n>0?'+':''}${n}`).join(' / ')}`;$('result').append(title,detail);for(let s=1;s<3;s++){const row=document.createElement('div');row.className='revealed-hand';row.textContent=`${names[s]}剩余：${game.revealed[s].map(c=>textRank(rank(c))).join(' ')||'已出完'}`;$('result').append(row);}}
 $('history').replaceChildren();for(const [s,rs] of [...game.history].reverse()){const li=document.createElement('li');li.textContent=`${names[s]}：${rs.length?rs.map(textRank).join(' '):'不出'}`;$('history').append(li);}if(!game.history.length){const li=document.createElement('li');li.textContent='尚未出牌';$('history').append(li);}
 if(game.last_ai){const d=game.last_ai;$('aiInfo').textContent=`${names[d.seat]} · Laya 推理 ${d.inference_ms} ms · 整步 ${Math.round(d.total_ms)} ms${d.intervened?' · 策略护栏介入':''}。${d.reason}。`;}
 else $('aiInfo').textContent='Laya 共享权重，各自只看自己的手牌与公开信息。';
 $('retry').hidden=!stopped;
}
function selection(){$('selection').textContent=selected.size?`已选 ${selected.size} 张`:'点选牌面，组合出牌';$('play').disabled=busy||!game||game.turn!==0||!selected.size;}
async function request(endpoint,extra={}){
 const response=await fetch('/api/'+endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,version:game?.version,...extra})});
 const data=await response.json();if(data.game)game=data.game;
 if(!response.ok)throw new Error(data.error||'请求失败');
 if(data.id){id=data.id;sessionStorage.setItem('ddz-table',id);}return data;
}
async function chain(){
 let actions=0;
 while(game&&game.phase!=='over'&&game.turn!==0&&!stopped){
  if(++actions>20)throw new Error('连续重发次数较多，请点击重试继续。');
  render();await wait(550);await request('step');render();
 }
}
async function act(endpoint,extra={}){
 if(busy)return;busy=true;stopped=false;notify();render();
 try{const data=await request(endpoint,extra);if(endpoint==='hint'){selected=new Set(data.suggested);notify(data.suggested.length?'已选中建议牌，可确认后出牌。':'建议本轮不出。');}else if(endpoint!=='state'){selected.clear();}await chain();}
 catch(e){stopped=true;notify(e.message||'无法连接本地服务，请检查启动终端。',true);}
 finally{busy=false;render();}
}
for(const b of document.querySelectorAll('[data-bid]'))b.addEventListener('click',()=>act('bid',{bid:+b.dataset.bid}));
$('play').addEventListener('click',()=>act('play',{cards:[...selected]}));$('pass').addEventListener('click',()=>act('play',{cards:[]}));$('hint').addEventListener('click',()=>act('hint'));$('clear').addEventListener('click',()=>{selected.clear();render();});
$('retry').addEventListener('click',()=>act(id?'state':'new'));$('nextRound').addEventListener('click',()=>act('next'));
$('newRound').addEventListener('click',()=>{if(game?.phase==='over'||confirm('结束当前这局并重新发牌？本局不计分。'))act('next');});
$('rulesButton').addEventListener('click',()=>$('rules').showModal());$('closeRules').addEventListener('click',()=>$('rules').close());
(async()=>{busy=true;try{const health=await fetch('/api/health').then(r=>r.json());$('connection').textContent=health.ready?'本地模型已连接':'模型尚未就绪';if(id){try{await request('state');}catch(e){if(e.message.includes('过期')){id=null;sessionStorage.removeItem('ddz-table');await request('new');}else throw e;}}else await request('new');render();await chain();}catch(e){stopped=true;notify(e.message||'连接失败，请确认服务正在运行。',true);$('connection').textContent='连接中断';$('retry').hidden=false;}finally{busy=false;render();}})();
