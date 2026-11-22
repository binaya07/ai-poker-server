const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function ui(withLeaderboard = false) {
  const elements = new Map();
  const sent = [];
  const element = () => ({ textContent: '', innerHTML: '', handlers: {}, children: [], parts: {},
    style: { setProperty() {} },
    appendChild(child) { this.children.push(child); },
    querySelector(selector) {
      if (selector === '.empty-chart') return null;
      return this.parts[selector] ||= element();
    },
    classList: { toggle() {} }, setAttribute() {},
    addEventListener(name, handler) { this.handlers[name] = handler; } });
  const context = vm.createContext({
    window: { location: { protocol: 'http:', host: 'localhost' } },
    document: { createElement: element, getElementById(id) {
      if (!elements.has(id)) elements.set(id, element());
      return elements.get(id);
    } },
    WebSocket: class { addEventListener() {} send(message) { sent.push(JSON.parse(message)); } },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../frontend/static/app.js'), 'utf8'), context);
  // Isolate status/board rendering from the separate animated leaderboard.
  if (!withLeaderboard) vm.runInContext('renderStackChart = () => {};', context);
  const render = (snapshot) => { context.snapshot = snapshot; vm.runInContext('renderState(snapshot)', context); };
  return { elements, sent, render };
}

function state(overrides = {}) {
  return { hand_number: 1, hands_completed: 0, max_hands: 2,
    phase: 'PREFLOP', current_turn: 'a', running: true, pot: 30,
    players: ['a', 'b'].map(id => ({ id, name: id, connected: true, stack: 980,
      bet: 20, profit_loss: 0, hands_played: 0, hole_cards: [{ label: '??' }, { label: '??' }] })),
    community_cards: [], ...overrides };
}

test('leaderboard displays and ranks available chips instead of profit', () => {
  const view = ui(true);
  const snapshot = state();
  Object.assign(snapshot.players[0], { stack: 400, profit_loss: 200 });
  Object.assign(snapshot.players[1], { stack: 1600, profit_loss: -200 });
  view.render(snapshot);
  const rows = view.elements.get('stack-chart').children;
  assert.equal(rows[0].parts['.stack-name'].textContent, 'b');
  assert.equal(rows[0].parts['.stack-value'].textContent, '$1,600');
  assert.equal(rows[1].parts['.stack-value'].textContent, '$400');
  assert.equal(rows[0].parts['.stack-value'].className, 'stack-value');
});

test('busted players sit out but live all-in players remain in the hand', () => {
  const view = ui();
  const snapshot = state();
  Object.assign(snapshot.players[0], { stack: 0, hole_cards: [], folded: true });
  Object.assign(snapshot.players[1], { stack: 0, all_in: true });
  view.render(snapshot);
  assert.match(view.elements.get('players').innerHTML, /Out of chips/);
  assert.match(view.elements.get('players').innerHTML, />All-in</);
});

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
  view.render(state({ hand_number: 0, phase: 'WAITING', current_turn: null, last_action: null }));
  view.render(state());
  assert.equal(button.textContent, 'Pause');
});

test('table shows chip amounts and final winner is chosen by stack, not profit', () => {
  const view = ui();
  const final = state({ phase: 'WAITING', match_complete: true });
  final.players[0].stack = 1500;
  final.players[0].profit_loss = -500;
  final.players[1].stack = 500;
  final.players[1].profit_loss = 500;
  final.players.forEach(p => p.hands_played = 1);
  view.render(final);
  assert.match(view.elements.get('players').innerHTML, /Chips: \$1,500/);
  assert.doesNotMatch(view.elements.get('players').innerHTML, /P\/L|profit|loss/);
  assert.match(view.elements.get('status-message').textContent, /Winner: a \(\$1,500\)/);
});
