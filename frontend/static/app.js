// The browser is an instructor observer. Bots receive separate private snapshots;
// this socket displays public state and may start hands without taking a seat.
const socket = new WebSocket(`${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`);

const stateEls = {
  phase: document.getElementById('phase-badge'),
  pot: document.getElementById('pot-display'),
  players: document.getElementById('players'),
  community: document.getElementById('community-cards'),
  tablePhase: document.getElementById('table-phase-text'),
  tablePot: document.getElementById('table-pot-text'),
  status: document.getElementById('status-message'),
  playButton: document.getElementById('play-button'),
  playStatus: document.getElementById('play-status'),
  stackChart: document.getElementById('stack-chart'),
  notifications: document.getElementById('notifications'),
  actionDelaySlider: document.getElementById('action-delay-slider'),
  actionDelayValue: document.getElementById('action-delay-value'),
  showdownRevealSlider: document.getElementById('showdown-reveal-slider'),
  showdownRevealValue: document.getElementById('showdown-reveal-value')
};

// Speed lives on the server so it paces every bot, not just the demo ones.
// Sliders send on release ('change'); the label tracks the drag ('input').
// While a slider is held, incoming snapshots don't yank it back.
const speedSliders = [
  { slider: stateEls.actionDelaySlider, value: stateEls.actionDelayValue, key: 'action_delay' },
  { slider: stateEls.showdownRevealSlider, value: stateEls.showdownRevealValue, key: 'showdown_reveal' }
];

for (const { slider, value } of speedSliders) {
  slider.addEventListener('input', () => { value.textContent = `${Number(slider.value).toFixed(1)}s`; });
  slider.addEventListener('change', () => {
    socket.send(JSON.stringify({
      type: 'set_speed',
      action_delay: Number(stateEls.actionDelaySlider.value),
      showdown_reveal: Number(stateEls.showdownRevealSlider.value)
    }));
  });
}

function renderSpeed(speed) {
  if (!speed) return;
  for (const { slider, value, key } of speedSliders) {
    if (document.activeElement === slider && slider.matches(':active')) continue;
    slider.value = speed[key];
    value.textContent = `${Number(speed[key]).toFixed(1)}s`;
  }
}

// One button drives continuous play: Start -> Pause <-> Continue. The server
// owns the running/paused flags; the button only asks to flip them and
// relabels itself from the next snapshot.
let gamePlaying = false;
let gameComplete = false;
stateEls.playButton.addEventListener('click', () => {
  socket.send(JSON.stringify({ type: gameComplete ? 'restart_match' : (gamePlaying ? 'pause' : 'resume') }));
});

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character]));
}

// cardsprites.png is a 13-col x 4-row grid: cols are rank 2..A left to right,
// rows are hearts, clubs, diamonds, spades top to bottom.
const SPRITE_SUIT_ROW = { hearts: 0, clubs: 1, diamonds: 2, spades: 3 };

function card(cardValue) {
  const hidden = cardValue.label === '??';
  if (hidden) {
    return '<div class="card hidden" aria-label="face-down card"></div>';
  }
  const col = cardValue.rank - 2;
  const row = SPRITE_SUIT_ROW[cardValue.suit];
  return `<div class="card" style="--col:${col}; --row:${row}" aria-label="${escapeHtml(cardValue.label)}"></div>`;
}

// Each bot keeps one color for the whole session, assigned in the order bots
// are first seen so the first ten are guaranteed distinct. Past the palette,
// golden-angle hue steps keep later colors spread out.
const PLAYER_PALETTE = ['#ff6b6b', '#4dabf7', '#ffd43b', '#69db7c', '#da77f2', '#ff922b', '#3bc9db', '#f783ac', '#a9e34b', '#9775fa'];
const playerColors = new Map();

function playerColor(playerId) {
  if (!playerColors.has(playerId)) {
    const index = playerColors.size;
    playerColors.set(playerId, index < PLAYER_PALETTE.length
      ? PLAYER_PALETTE[index]
      : `hsl(${Math.round((index * 137.508) % 360)}, 75%, 65%)`);
  }
  return playerColors.get(playerId);
}

function formatChips(amount) {
  return `$${amount.toLocaleString()}`;
}

// Tracks each player's most recent decision so it can render above their
// name. The engine only exposes a single table-wide last_action, so this
// persists across renders and resets whenever a new hand deals.
const lastActionByPlayer = {};

function describeAction(action) {
  switch (action.type) {
    case 'fold':
      return { player: action.player, text: 'Folded' };
    case 'check':
      return { player: action.player, text: 'Checked' };
    case 'call':
      return { player: action.player, text: `Called $${action.amount}` };
    case 'raise':
      return { player: action.player, text: `Raised to $${action.target}` };
    default:
      return null;
  }
}

function updateLastActions(action) {
  if (!action) return;
  if (action.type === 'deal') {
    Object.keys(lastActionByPlayer).forEach((key) => delete lastActionByPlayer[key]);
    lastActionByPlayer[action.small_blind] = 'Posted small blind';
    lastActionByPlayer[action.big_blind] = 'Posted big blind';
    return;
  }
  const described = describeAction(action);
  if (described) lastActionByPlayer[described.player] = described.text;
}

// Leaderboard rows are kept as persistent DOM nodes (keyed by player id)
// rather than rebuilt every render, so animating `top` on rank changes
// actually produces a slide instead of a instant jump.
const STACK_ROW_HEIGHT = 48;
const stackRowEls = new Map();

function renderStackChart(players) {
  if (!players.length) {
    stateEls.stackChart.innerHTML = '<div class="empty-chart">Waiting for bots…</div>';
    stackRowEls.clear();
    return;
  }
  const stray = stateEls.stackChart.querySelector('.empty-chart');
  if (stray) stray.remove();

  const ranked = [...players].sort((a, b) => b.stack - a.stack);
  const seen = new Set();
  ranked.forEach((player, index) => {
    seen.add(player.id);
    let row = stackRowEls.get(player.id);
    if (!row) {
      row = document.createElement('div');
      row.className = 'stack-row';
      row.innerHTML = '<span class="stack-rank"></span><span class="stack-swatch"></span><span class="stack-name"></span><span class="stack-value"></span>';
      row.style.setProperty('--player-color', playerColor(player.id));
      row.style.top = `${index * STACK_ROW_HEIGHT}px`;
      stateEls.stackChart.appendChild(row);
      stackRowEls.set(player.id, row);
    }
    row.title = `${player.name}: ${formatChips(player.stack)} available chips; ${player.hands_played || 0} hands played`;
    row.querySelector('.stack-rank').textContent = `${index + 1}`;
    row.querySelector('.stack-name').textContent = player.name;
    row.querySelector('.stack-name').title = player.name;
    row.querySelector('.stack-value').textContent = formatChips(player.stack);
    row.querySelector('.stack-value').className = 'stack-value';
    row.style.top = `${index * STACK_ROW_HEIGHT}px`;
  });
  for (const [id, row] of stackRowEls) {
    if (!seen.has(id)) {
      row.remove();
      stackRowEls.delete(id);
    }
  }
  stateEls.stackChart.style.height = `${ranked.length * STACK_ROW_HEIGHT}px`;
}

let displayedHand = -1;

function playerStatus(player, snapshot) {
  if (!player.connected) return 'Disconnected';
  if (snapshot.match_complete) return 'Match finished';
  if (player.stack === 0 && !player.all_in) return 'Out of chips';
  if (snapshot.phase === 'WAITING' && player.stack === 0) return 'Out of chips';
  if (snapshot.phase === 'WAITING') return snapshot.hand_number ? 'Hand finished' : 'Ready';
  if (!(player.hole_cards || []).length) return 'Joining next hand';
  if (player.folded) return 'Folded';
  if (snapshot.phase === 'SHOWDOWN') return 'Showing hand';
  if (player.all_in) return 'All-in';
  if (snapshot.current_turn === player.id) return snapshot.paused ? 'Paused — to act' : 'To act';
  return 'Waiting for turn';
}

function renderState(snapshot) {
  // Restart broadcasts the existing empty hand-zero state before dealing.
  const reset = snapshot.hand_number === 0 && snapshot.phase === 'WAITING' && snapshot.last_action == null;
  if (!reset && snapshot.hand_number < displayedHand) return;
  if (reset || snapshot.hand_number !== displayedHand) {
    Object.keys(lastActionByPlayer).forEach(key => delete lastActionByPlayer[key]);
    displayedHand = snapshot.hand_number;
  }
  const canStart = Boolean(snapshot.can_start);
  const started = Boolean(snapshot.running);
  const gamePaused = Boolean(snapshot.paused);
  const complete = Boolean(snapshot.match_complete);
  gameComplete = complete;
  gamePlaying = started && !gamePaused && !complete;
  stateEls.playButton.disabled = false;
  stateEls.playButton.textContent = complete ? 'Restart match' : (gamePlaying ? 'Pause' : (started ? 'Continue' : 'Start'));
  stateEls.playButton.classList.toggle('playing', gamePlaying);
  stateEls.playButton.setAttribute('aria-pressed', String(gamePlaying));
  stateEls.playStatus.textContent = complete
    ? `Match finished after ${snapshot.hands_completed} hands (limit ${snapshot.max_hands})`
    : `${gamePaused ? 'Paused' : (started ? 'Playing' : 'Ready')} · Hand ${snapshot.hand_number} of ${snapshot.max_hands} · ${snapshot.hands_completed} completed`;
  renderSpeed(snapshot.speed);
  stateEls.phase.textContent = snapshot.phase;
  stateEls.pot.textContent = `Pot: $${snapshot.pot}`;
  stateEls.tablePhase.textContent = snapshot.phase;
  stateEls.tablePot.textContent = `Pot: $${snapshot.pot}`;
  updateLastActions(snapshot.last_action);
  // Retain the result in server snapshots, but clear the visual board between hands.
  const board = ['WAITING', 'PREFLOP'].includes(snapshot.phase) ? [] : (snapshot.community_cards || []);
  const community = board.map(card).join('');
  const placeholders = Array.from({ length: Math.max(0, 5 - board.length) }, () => '<div class="card hidden" aria-label="face-down card"></div>').join('');
  stateEls.community.innerHTML = community + placeholders;
  const players = snapshot.players || [];
  stateEls.players.innerHTML = players.map((player) => {
    const turn = snapshot.current_turn === player.id;
    const state = playerStatus(player, snapshot);
    return `<div class="player-seat ${turn ? 'current-turn' : ''} ${player.folded && snapshot.phase !== 'WAITING' ? 'folded' : ''}" style="--player-color:${playerColor(player.id)}">
      <div class="player-last-action">${escapeHtml(lastActionByPlayer[player.id] || '')}</div>
      <div class="player-name"><span class="player-name-text" title="${escapeHtml(player.name)}">${escapeHtml(player.name)}</span>${snapshot.dealer === player.id ? '<span class="dealer-chip" title="Dealer" aria-label="Dealer">D</span>' : ''}${snapshot.small_blind_player === player.id ? '<span class="blind-chip small-blind-chip" title="Small blind" aria-label="Small blind">SB</span>' : ''}${snapshot.big_blind_player === player.id ? '<span class="blind-chip big-blind-chip" title="Big blind" aria-label="Big blind">BB</span>' : ''}</div>
      <div class="player-hole">${(player.hole_cards || []).map(card).join('')}</div>
      <div class="player-stack">Chips: ${formatChips(player.stack)}</div>
      <div class="player-bet">Street bet: $${player.bet}</div>
      <div class="player-hands">Hands played: ${player.hands_played || 0}</div>
      <div class="player-state">${state}</div>
    </div>`;
  }).join('');
  renderStackChart(players);
  const action = snapshot.last_action;
  if (complete) {
    const eligible = players.filter(p => p.hands_played > 0);
    const best = Math.max(...eligible.map(p => p.stack));
    const leaders = eligible.filter(p => p.stack === best).map(p => p.name);
    stateEls.status.textContent = `Match complete. ${leaders.length > 1 ? 'Joint winners' : 'Winner'}: ${leaders.join(', ')} (${formatChips(best)}). Press Restart match to reset chips and play again with the same bots.`;
  } else if (gamePaused) {
    stateEls.status.textContent = 'Game paused. Press Continue to resume play.';
  } else if (snapshot.phase === 'SHOWDOWN') {
    stateEls.status.textContent = 'Showdown — revealing hands before payout.';
  } else if (action?.type === 'payout') {
    stateEls.status.textContent = `Hand complete — ${Object.keys(action.payouts || {}).join(', ') || action.winners.join(', ')} collected the pot.`;
  } else if (snapshot.current_turn) {
    stateEls.status.textContent = `Hand ${snapshot.hand_number}: waiting for ${snapshot.current_turn}.`;
  } else if (!started) {
    stateEls.status.textContent = canStart ? 'Bots are seated. Press Start to begin the match.' : 'Waiting for at least two connected bots with chips.';
  } else if (snapshot.phase === 'WAITING' && !canStart) {
    stateEls.status.textContent = 'Fewer than two connected bots have chips. Waiting for eligible bots to join or reconnect.';
  } else {
    stateEls.status.textContent = 'Dealing the next hand…';
  }
}

socket.addEventListener('open', () => socket.send(JSON.stringify({ type: 'observe' })));
socket.addEventListener('message', (event) => {
  const message = JSON.parse(event.data);
  if (message.type === 'state') renderState(message.payload);
  if (message.type === 'error') stateEls.status.textContent = message.message;
});
socket.addEventListener('close', () => { stateEls.status.textContent = 'Disconnected from the table display.'; });
