const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function ui() {
  const elements = new Map();
  const sent = [];
  const element = () => ({ textContent: '', innerHTML: '', handlers: {},
    classList: { toggle() {} }, setAttribute() {},
    addEventListener(name, handler) { this.handlers[name] = handler; } });
  const context = vm.createContext({
    window: { location: { protocol: 'http:', host: 'localhost' } },
    document: { getElementById(id) {
      if (!elements.has(id)) elements.set(id, element());
      return elements.get(id);
    } },
    WebSocket: class { addEventListener() {} send(message) { sent.push(JSON.parse(message)); } },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../frontend/static/app.js'), 'utf8'), context);
  // Isolate status/board rendering from the separate animated leaderboard.
  vm.runInContext('renderStackChart = () => {};', context);
  const render = (snapshot) => { context.snapshot = snapshot; vm.runInContext('renderState(snapshot)', context); };
  return { elements, sent, render };
}

function state(overrides = {}) {
  return { match_number: 1, hand_number: 1, hands_completed: 0, max_hands: 2,
    phase: 'PREFLOP', current_turn: 'a', running: true, pot: 30,
    players: ['a', 'b'].map(id => ({ id, name: id, connected: true, stack: 980,
      bet: 20, profit_loss: 0, hands_played: 0, hole_cards: [{ label: '??' }, { label: '??' }] })),
    community_cards: [], ...overrides };
}

test('active player, waiting opponent, showdown and late join have distinct labels', () => {
  const view = ui();
  view.render(state());
  let markup = view.elements.get('players').innerHTML;
  assert.equal((markup.match(/>To act</g) || []).length, 1);
  assert.equal((markup.match(/>Waiting for turn</g) || []).length, 1);
  view.render(state({ phase: 'SHOWDOWN', current_turn: null }));
  markup = view.elements.get('players').innerHTML;
  assert.equal((markup.match(/>Showing hand</g) || []).length, 2);
  assert.ok(!markup.includes('Waiting for turn'));
  const late = state();
  late.players[1].hole_cards = [];
  view.render(late);
  assert.match(view.elements.get('players').innerHTML, /Joining next hand/);
});

test('manual hands still identify the current player and paused turns are explicit', () => {
  const view = ui();
  view.render(state({ running: false }));
  assert.match(view.elements.get('status-message').textContent, /waiting for a/);
  view.render(state({ paused: true }));
  assert.match(view.elements.get('players').innerHTML, /Paused — to act/);
});

test('board clears between hands and old snapshots cannot restore it', () => {
  const view = ui();
  const cards = [{ rank: 14, suit: 'spades', label: 'AS' }];
  view.render(state({ phase: 'RIVER', community_cards: cards }));
  assert.match(view.elements.get('community-cards').innerHTML, /aria-label="AS"/);
  view.render(state({ phase: 'WAITING', current_turn: null, community_cards: cards }));
  assert.doesNotMatch(view.elements.get('community-cards').innerHTML, /aria-label="AS"/);
  view.render(state({ hand_number: 2 }));
  view.render(state({ phase: 'RIVER', community_cards: cards }));
  assert.doesNotMatch(view.elements.get('community-cards').innerHTML, /aria-label="AS"/);
  assert.equal(view.elements.get('table-phase-text').textContent, 'PREFLOP');
});

test('restart button sends observer command and accepts a new match starting at hand one', () => {
  const view = ui();
  const final = state({ hand_number: 2, hands_completed: 2, phase: 'WAITING', match_complete: true });
  final.players.forEach(p => p.hands_played = 2);
  view.render(final);
  const button = view.elements.get('play-button');
  assert.equal(button.textContent, 'Restart match');
  assert.equal(button.disabled, false);
  button.handlers.click();
  assert.deepEqual(view.sent, [{ type: 'restart_match' }]);
  view.render(state({ match_number: 2 }));
  assert.equal(button.textContent, 'Pause');
  view.render(final);
  assert.equal(button.textContent, 'Pause');
});
