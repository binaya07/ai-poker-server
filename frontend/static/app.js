// The browser is deliberately a read-only table display. Bots connect separately
// and receive their own private snapshots; this socket only subscribes as observer.
const socket = new WebSocket(`${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`);
const uiPlayerId = 'ui-host';
const uiPlayerName = 'Table Host';

const stateEls = {
  phase: document.getElementById('phase-badge'),
  pot: document.getElementById('pot-display'),
  players: document.getElementById('players'),
  community: document.getElementById('community-cards'),
  dealer: document.getElementById('dealer-mark'),
  status: document.getElementById('status-message'),
  startButton: document.getElementById('start-hand-button')
};

let hasJoinedUiSeat = false;

stateEls.startButton.addEventListener('click', () => {
  if (!hasJoinedUiSeat) {
    socket.send(JSON.stringify({ type: 'join', player_id: uiPlayerId, name: uiPlayerName }));
    hasJoinedUiSeat = true;
    return;
  }

  socket.send(JSON.stringify({ type: 'start_hand' }));
});

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character]));
}

function card(cardValue) {
  const hidden = cardValue.label === '??';
  return `<div class="card ${hidden ? 'hidden' : ''}">${hidden ? '?' : escapeHtml(cardValue.label)}</div>`;
}

function renderState(snapshot) {
  const canStart = Boolean(snapshot.can_start);
  stateEls.startButton.disabled = !canStart || snapshot.phase !== 'WAITING';
  stateEls.phase.textContent = snapshot.phase;
  stateEls.pot.textContent = `Pot: $${snapshot.pot}`;
  stateEls.dealer.textContent = `Dealer: ${snapshot.dealer || 'None'}`;
  const community = (snapshot.community_cards || []).map(card).join('');
  const placeholders = Array.from({ length: Math.max(0, 5 - (snapshot.community_cards || []).length) }, () => '<div class="card hidden">?</div>').join('');
  stateEls.community.innerHTML = community + placeholders;
  stateEls.players.innerHTML = (snapshot.players || []).map((player) => {
    const turn = snapshot.current_turn === player.id;
    const state = player.folded ? 'Folded' : (player.all_in ? 'All-in' : (turn ? 'Acting' : 'Waiting'));
    return `<div class="player-seat ${turn ? 'current-turn' : ''} ${player.folded ? 'folded' : ''}">
      <div class="player-name">${escapeHtml(player.name)}</div>
      <div class="player-stack">Stack: $${player.stack}</div>
      <div class="player-bet">Street bet: $${player.bet}</div>
      <div class="player-state">${state}</div>
      <div class="player-hole">${(player.hole_cards || []).map(card).join('')}</div>
    </div>`;
  }).join('');
  const action = snapshot.last_action;
  if (action?.type === 'payout') {
    stateEls.status.textContent = `Hand complete — ${Object.keys(action.payouts || {}).join(', ') || action.winners.join(', ')} collected the pot.`;
  } else if (!canStart) {
    stateEls.status.textContent = 'Need at least two connected players with chips to start a hand.';
  } else if (snapshot.current_turn) {
    stateEls.status.textContent = `Hand ${snapshot.hand_number}: waiting for ${snapshot.current_turn}.`;
  } else {
    stateEls.status.textContent = 'Waiting for bots to join or start a hand.';
  }
}

socket.addEventListener('open', () => socket.send(JSON.stringify({ type: 'observe' })));
socket.addEventListener('message', (event) => {
  const message = JSON.parse(event.data);
  if (message.type === 'state') renderState(message.payload);
  if (message.type === 'error') stateEls.status.textContent = message.message;
});
socket.addEventListener('close', () => { stateEls.status.textContent = 'Disconnected from the table display.'; });
