# Демо-данные для скриншотов: запускается из корня проекта при работающем приложении на :8010 (см. README.md в этой папке)
import json, random, re, httpx
BASE="http://localhost:8010"
HEAD={"Origin":BASE}
PW="demo-password-1"
cards=json.load(open("data/cards.json",encoding="utf-8"))
by_term={c["term"]:c for c in cards}
random.seed(7)

def client(): return httpx.Client(base_url=BASE,headers=HEAD,timeout=30)

def register(name,role="student"):
    c=client(); r=c.post("/auth/register",json={"name":name,"password":PW,"password_confirm":PW,"role":role}); assert r.status_code==201,r.text; return c

def solve(task):
    t=task["task_type"]; p=task["prompt"]; opts=task.get("options") or []
    if t=="definition_match": return by_term[p]["definition_en"] if p in by_term else opts[0]
    if t=="gap_fill":
        for o in opts:
            c=by_term.get(o)
            if c and any(re.sub(r"\b"+re.escape(o)+r"\w*","____",e,flags=re.I)==p for e in c["examples"]): return o
        return opts[0]
    if t=="spelling_choice": return next((o for o in opts if o in by_term),opts[0])
    if t=="collocation_choice":
        for o in opts:
            if any(p.replace("____",o)==col for c in cards for col in c["collocations"]): return o
        return opts[0]
    if t=="write_term": return next((c["term"] for c in cards if c["definition_en"]==p),"x")
    if t=="explain_meaning": return by_term.get(p,{}).get("definition_en","A word.")
    if t=="compose_sentence":
        term=p.split(" - ")[0]; return by_term[term]["examples"][0]
    return "x"

def wrong(task,right):
    opts=task.get("options")
    if opts: return random.choice([o for o in opts if o!=right] or opts)
    return "wrong answer"

def practise(c,accuracy,limit=14):
    c.put("/me/settings",json={"new_cards_per_day":8})
    for _ in range(limit):
        data=c.get("/session/next").json()
        task=data.get("task")
        if not task: break
        right=solve(task)
        text=right if random.random()<accuracy else wrong(task,right)
        r=c.post("/session/answer",json={"card_id":task["card_id"],"task_type":task["task_type"],"answer":text,"task_id":task.get("task_id"),"context":task.get("context")})
        assert r.status_code==200,r.text

teacher=register("ivanova_t","teacher")
groups={}
for name in ("IT-21","IT-22"):
    groups[name]=teacher.post("/teacher/groups",json={"name":name}).json()["id"]
students={"anna_k":(0.85,"IT-21"),"boris_dev":(0.55,"IT-21"),"clara_sec":(0.7,"IT-22"),"denis_ops":(0.4,"IT-22")}
sessions={}
for nick,(acc,group) in students.items():
    c=register(nick); sessions[nick]=c
    assert c.post("/me/teachers/requests",json={"name":"ivanova_t"}).status_code==202
for req in teacher.get("/teacher/links").json()["requests"]:
    group=students[req["name"]][1]
    assert teacher.post(f"/teacher/requests/{req['id']}/accept",json={"group_id":groups[group]}).status_code==204
# карточка и набор преподавателя, назначенный группе IT-21
card={"term":"ciphertext","transcription":"/ˈsaɪfərtekst/","part_of_speech":"noun","definition_en":"Data that has been encrypted and cannot be read without the key.","translation_ru":"шифротекст","collocations":["decrypt ciphertext","encrypted ciphertext"],"examples":["The attacker intercepted the ciphertext.","Without the key, the ciphertext is unreadable."],"common_mistakes":["Confusing ciphertext with plaintext."],"contrast_term":"plaintext","domain":"Information security"}
cid=teacher.post("/teacher/cards",json=card).json()["id"]
did=teacher.post("/teacher/decks",json={"name":"Cryptography basics","description":"Термины по шифрованию","domain":"Information security"}).json()["id"]
teacher.put(f"/teacher/decks/{did}/cards",json={"card_ids":[cid]})
teacher.put(f"/teacher/decks/{did}/groups",json={"group_ids":[groups["IT-21"]]})
for nick,(acc,_) in students.items(): practise(sessions[nick],acc)
import subprocess
subprocess.run(["docker","compose","exec","-T","postgres","sh","-c","psql -U \"$POSTGRES_USER\" -d vocab_shots -c \"UPDATE review_history SET answered_on = answered_on - 1, created_at = created_at - interval '1 day'; UPDATE card_progress SET first_seen_on = first_seen_on - 1, due_date = current_date, repetitions = (id % 6), last_error_type = NULL, pending_interval = NULL;\""],check=True)
for nick,(acc,_) in students.items():
    c=sessions[nick]; practise(c,acc,limit=14)
# студент anna_k ждет ответа на приглашение второго преподавателя
t2=register("petrov_t","teacher")
t2.post("/teacher/invitations",json={"name":"anna_k","group_id":None})
print("ok", [ (n, sessions[n].get("/me/stats").json()["totals"]) for n in students])
