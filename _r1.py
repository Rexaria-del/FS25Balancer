import io
def rd(p):
    with io.open(p, encoding='utf-8') as f: return f.read().replace('\r\n', '\n')
def rep(path, old, new, tag):
    s = rd(path)
    if old not in s:
        print('MISS ' + tag); return
    with io.open(path, 'w', encoding='utf-8', newline='') as f: f.write(s.replace(old, new, 1))
    print('OK   ' + tag)

C = r'C:\FS25Balancer\web\css\app.css'

# 1) убираем вложенный скроллер — один скролл на всю вкладку
rep(C, '#aiList { max-height: min(640px, 62vh); overflow: auto; padding-right: 4px; }',
       '#aiList { padding-right: 4px; }', 'css.ailist_flat')

# 2) пульсация рекомендации: перелив цветов + мягкое дыхание + шиммер бейджа
rep(C, '''.ai-i.is-rec { border-color: rgba(99, 102, 241, .55); background: rgba(99, 102, 241, .09);
  animation: recBreath 4.6s ease-in-out .6s infinite; }
@keyframes recBreath { 0%, 100% { box-shadow: 0 0 0 0 rgba(99, 102, 241, 0); }
  50% { box-shadow: 0 0 22px -4px rgba(99, 102, 241, .34); } }''',
'''.ai-i.is-rec { position: relative; background: linear-gradient(90deg,
    rgba(99,102,241,.14), rgba(34,211,238,.14), rgba(139,92,246,.14), rgba(99,102,241,.14));
  background-size: 300% 100%; animation: recFlow 3.4s linear infinite, recPulse 2.4s ease-in-out infinite, recScale 2.4s ease-in-out infinite; }
.ai-i.is-rec::before { content: ""; position: absolute; inset: -1.5px; border-radius: inherit; padding: 1.5px;
  background: linear-gradient(115deg, #6366f1, #22d3ee, #8b5cf6, #6366f1); background-size: 300% 100%;
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor; mask-composite: exclude; animation: recFlow 3.4s linear infinite; pointer-events: none; }
@keyframes recFlow { 0% { background-position: 0% 50%; } 100% { background-position: 300% 50%; } }
@keyframes recPulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(99, 102, 241, 0); }
  50% { box-shadow: 0 0 26px -2px rgba(99, 102, 241, .55); } }
@keyframes recScale { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.014); } }
.ai-i.is-rec .rec-badge { animation: badgeShift 2.4s ease-in-out infinite; }
@keyframes badgeShift { 0%, 100% { background: rgba(99, 102, 241, .28); color: #c7d2fe; }
  33% { background: rgba(34, 211, 238, .30); color: #cffafe; } 66% { background: rgba(139, 92, 246, .30); color: #ede9fe; } }''',
'css.rec_pulse')

print('DONE')
