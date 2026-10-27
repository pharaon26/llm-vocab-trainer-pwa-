import pytest
from sqlalchemy import func, select

from app.config import link_config
from app.models import LinkRequest, TeacherGroup, TeacherStudent, User
from tests.conftest import login


async def user_id(db, name):
    return await db.scalar(select(User.id).where(func.lower(User.name) == name.lower()))


@pytest.fixture
async def people(client):
    return {
        "t1": await login(client, name="teach_one", role="teacher"),
        "t2": await login(client, name="teach_two", role="teacher"),
        "s1": await login(client, name="stud_one"),
        "s2": await login(client, name="stud_two"),
    }


async def group(client, headers, name="Group A"):
    response = await client.post("/teacher/groups", headers=headers, json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def invite(client, headers, nickname, group_id=None):
    return await client.post("/teacher/invitations", headers=headers, json={"name": nickname, "group_id": group_id})


async def ask(client, headers, nickname):
    return await client.post("/me/teachers/requests", headers=headers, json={"name": nickname})


async def my_teachers(client, headers):
    return (await client.get("/me/teachers", headers=headers)).json()


async def teacher_links(client, headers):
    return (await client.get("/teacher/links", headers=headers)).json()


async def linked(db, teacher, student):
    return await db.get(TeacherStudent, (await user_id(db, teacher), await user_id(db, student))) is not None


async def test_invitation_flow_links_only_after_the_student_accepts(client, db, people):
    gid = await group(client, people["t1"])
    assert (await invite(client, people["t1"], "stud_one", gid)).status_code == 202
    assert not await linked(db, "teach_one", "stud_one")
    mine = await my_teachers(client, people["s1"])
    assert mine["teachers"] == [] and [i["name"] for i in mine["invitations"]] == ["teach_one"]
    assert (await client.post(f"/me/invitations/{mine['invitations'][0]['id']}/accept", headers=people["s1"])).status_code == 204
    assert await linked(db, "teach_one", "stud_one")
    link = await db.get(TeacherStudent, (await user_id(db, "teach_one"), await user_id(db, "stud_one")))
    assert link.group_id == gid
    mine = await my_teachers(client, people["s1"])
    assert [t["name"] for t in mine["teachers"]] == ["teach_one"] and mine["invitations"] == []
    assert (await teacher_links(client, people["t1"]))["invitations"] == []


async def test_request_flow_links_only_after_the_teacher_accepts_with_a_group(client, db, people):
    gid = await group(client, people["t1"])
    assert (await ask(client, people["s1"], "teach_one")).status_code == 202
    assert not await linked(db, "teach_one", "stud_one")
    pending = (await teacher_links(client, people["t1"]))["requests"]
    assert [r["name"] for r in pending] == ["stud_one"]
    assert (await client.post(f"/teacher/requests/{pending[0]['id']}/accept", headers=people["t1"], json={"group_id": gid})).status_code == 204
    link = await db.get(TeacherStudent, (await user_id(db, "teach_one"), await user_id(db, "stud_one")))
    assert link.group_id == gid


async def test_students_request_lists_show_what_they_sent(client, people):
    await ask(client, people["s1"], "teach_one")
    assert [r["name"] for r in (await my_teachers(client, people["s1"]))["requests"]] == ["teach_one"]


async def test_declined_invitation_creates_no_link_and_cannot_be_reused(client, db, people):
    await invite(client, people["t1"], "stud_one")
    request_id = (await my_teachers(client, people["s1"]))["invitations"][0]["id"]
    assert (await client.post(f"/me/invitations/{request_id}/decline", headers=people["s1"])).status_code == 204
    assert not await linked(db, "teach_one", "stud_one")
    assert (await client.post(f"/me/invitations/{request_id}/accept", headers=people["s1"])).status_code == 404
    assert (await my_teachers(client, people["s1"]))["invitations"] == []


async def test_declined_request_creates_no_link(client, db, people):
    await ask(client, people["s1"], "teach_one")
    request_id = (await teacher_links(client, people["t1"]))["requests"][0]["id"]
    assert (await client.post(f"/teacher/requests/{request_id}/decline", headers=people["t1"])).status_code == 204
    assert not await linked(db, "teach_one", "stud_one")
    assert (await client.post(f"/teacher/requests/{request_id}/accept", headers=people["t1"], json={})).status_code == 404


async def test_a_new_invitation_is_possible_after_a_decline(client, people):
    await invite(client, people["t1"], "stud_one")
    first = (await my_teachers(client, people["s1"]))["invitations"][0]["id"]
    await client.post(f"/me/invitations/{first}/decline", headers=people["s1"])
    await invite(client, people["t1"], "stud_one")
    assert len((await my_teachers(client, people["s1"]))["invitations"]) == 1


async def test_mutual_consent_links_without_extra_steps(client, db, people):
    gid = await group(client, people["t1"])
    await ask(client, people["s1"], "teach_one")
    await invite(client, people["t1"], "stud_one", gid)
    assert await linked(db, "teach_one", "stud_one")
    link = await db.get(TeacherStudent, (await user_id(db, "teach_one"), await user_id(db, "stud_one")))
    assert link.group_id == gid
    assert (await teacher_links(client, people["t1"]))["requests"] == []


async def test_mutual_consent_the_other_way_round(client, db, people):
    gid = await group(client, people["t1"])
    await invite(client, people["t1"], "stud_one", gid)
    await ask(client, people["s1"], "teach_one")
    assert await linked(db, "teach_one", "stud_one")
    assert (await db.get(TeacherStudent, (await user_id(db, "teach_one"), await user_id(db, "stud_one")))).group_id == gid


async def test_repeated_invitations_do_not_pile_up(client, db, people):
    for _ in range(3):
        await invite(client, people["t1"], "stud_one")
    assert await db.scalar(select(func.count()).select_from(LinkRequest)) == 1


async def test_either_side_can_break_the_link(client, db, people):
    for teacher, student in (("t1", "s1"), ("t1", "s2")):
        await invite(client, people[teacher], "stud_one" if student == "s1" else "stud_two")
    for key in ("s1", "s2"):
        pending = (await my_teachers(client, people[key]))["invitations"][0]["id"]
        await client.post(f"/me/invitations/{pending}/accept", headers=people[key])
    assert (await client.delete("/me/teachers/teach_one", headers=people["s1"])).status_code == 204
    assert not await linked(db, "teach_one", "stud_one")
    assert (await client.delete("/me/teachers/teach_one", headers=people["s1"])).status_code == 404
    assert (await client.delete("/teacher/students/stud_two", headers=people["t1"])).status_code == 204
    assert not await linked(db, "teach_one", "stud_two")
    assert (await client.delete("/teacher/students/stud_two", headers=people["t1"])).status_code == 404


async def test_one_student_can_have_several_teachers(client, db, people):
    await invite(client, people["t1"], "stud_one")
    await invite(client, people["t2"], "stud_one")
    for item in (await my_teachers(client, people["s1"]))["invitations"]:
        await client.post(f"/me/invitations/{item['id']}/accept", headers=people["s1"])
    names = [t["name"] for t in (await my_teachers(client, people["s1"]))["teachers"]]
    assert names == ["teach_one", "teach_two"]


async def test_cancelling_own_invitation_and_request(client, db, people):
    await invite(client, people["t1"], "stud_one")
    invitation = (await teacher_links(client, people["t1"]))["invitations"][0]["id"]
    assert (await client.delete(f"/teacher/invitations/{invitation}", headers=people["t1"])).status_code == 204
    assert (await my_teachers(client, people["s1"]))["invitations"] == []
    await ask(client, people["s1"], "teach_one")
    request = (await my_teachers(client, people["s1"]))["requests"][0]["id"]
    assert (await client.delete(f"/me/requests/{request}", headers=people["s1"])).status_code == 204
    assert (await teacher_links(client, people["t1"]))["requests"] == []


async def test_groups_crud_and_names(client, db, people):
    gid = await group(client, people["t1"], "Alpha")
    assert (await client.post("/teacher/groups", headers=people["t1"], json={"name": "alpha"})).status_code == 409
    assert (await client.post("/teacher/groups", headers=people["t2"], json={"name": "Alpha"})).status_code == 201
    renamed = await client.put(f"/teacher/groups/{gid}", headers=people["t1"], json={"name": "Beta"})
    assert renamed.json()["name"] == "Beta"
    second = await group(client, people["t1"], "Gamma")
    assert (await client.put(f"/teacher/groups/{second}", headers=people["t1"], json={"name": "beta"})).status_code == 409
    assert [g["name"] for g in (await client.get("/teacher/groups", headers=people["t1"])).json()] == ["Beta", "Gamma"]
    assert (await client.post("/teacher/groups", headers=people["t1"], json={"name": "  "})).status_code == 422
    assert (await client.delete(f"/teacher/groups/{second}", headers=people["t1"])).status_code == 204


async def test_move_student_between_groups_and_deleting_a_group_keeps_students(client, db, people):
    first, second = await group(client, people["t1"], "One"), await group(client, people["t1"], "Two")
    await invite(client, people["t1"], "stud_one", first)
    request_id = (await my_teachers(client, people["s1"]))["invitations"][0]["id"]
    await client.post(f"/me/invitations/{request_id}/accept", headers=people["s1"])
    teacher_id, student_id = await user_id(db, "teach_one"), await user_id(db, "stud_one")
    assert (await client.put("/teacher/students/stud_one/group", headers=people["t1"], json={"group_id": second})).status_code == 204
    assert (await db.get(TeacherStudent, (teacher_id, student_id))).group_id == second
    groups = {g["name"]: g["students"] for g in (await client.get("/teacher/groups", headers=people["t1"])).json()}
    assert groups == {"One": 0, "Two": 1}
    await client.delete(f"/teacher/groups/{second}", headers=people["t1"])
    assert await linked(db, "teach_one", "stud_one")
    assert (await db.get(TeacherStudent, (teacher_id, student_id))).group_id is None
    assert (await client.put("/teacher/students/stud_one/group", headers=people["t1"], json={"group_id": None})).status_code == 204


async def test_search_answers_are_identical_for_every_outcome(client, db, people):
    await invite(client, people["t1"], "stud_two")
    request_id = (await my_teachers(client, people["s2"]))["invitations"][0]["id"]
    await client.post(f"/me/invitations/{request_id}/accept", headers=people["s2"])
    outcomes = []
    for nickname in ("stud_one", "STUD_ONE", "nobody_here", "teach_two", "stud_two", "x" * 50):
        response = await invite(client, people["t1"], nickname)
        outcomes.append((response.status_code, response.json()))
    assert len(set(map(str, outcomes))) == 1 and outcomes[0][0] == 202
    student_side = []
    for nickname in ("teach_one", "TEACH_ONE", "nobody_here", "stud_one", "teach_two"):
        response = await ask(client, people["s1"], nickname)
        student_side.append((response.status_code, response.json()))
    assert len(set(map(str, student_side))) == 1 and student_side[0][0] == 202


async def test_wrong_role_target_creates_nothing(client, db, people):
    await invite(client, people["t1"], "teach_two")
    await ask(client, people["s1"], "stud_two")
    assert await db.scalar(select(func.count()).select_from(LinkRequest)) == 0


async def test_invitations_and_requests_are_rate_limited(client, people):
    for index in range(link_config.max_attempts):
        assert (await invite(client, people["t1"], f"ghost_{index}")).status_code == 202
    assert (await invite(client, people["t1"], "stud_one")).status_code == 429
    for index in range(link_config.max_attempts):
        assert (await ask(client, people["s1"], f"ghost_{index}")).status_code == 202
    assert (await ask(client, people["s1"], "teach_one")).status_code == 429
    assert (await invite(client, people["t2"], "stud_one")).status_code == 202


async def test_rate_limit_window_expires(client, db, people):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from app.models import LinkAttempt

    for index in range(link_config.max_attempts):
        await invite(client, people["t1"], f"ghost_{index}")
    assert (await invite(client, people["t1"], "stud_one")).status_code == 429
    await db.execute(update(LinkAttempt).values(created_at=datetime.now(UTC) - timedelta(minutes=link_config.window_minutes + 1)))
    await db.commit()
    assert (await invite(client, people["t1"], "stud_one")).status_code == 202


async def test_invitation_validation(client, people):
    assert (await client.post("/teacher/invitations", headers=people["t1"], json={})).status_code == 422
    assert (await client.post("/teacher/invitations", headers=people["t1"], json={"name": ""})).status_code == 422


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/teacher/groups"), ("post", "/teacher/groups"), ("get", "/teacher/links"),
        ("post", "/teacher/invitations"), ("delete", "/teacher/students/x"), ("put", "/teacher/students/x/group"),
        ("post", "/teacher/requests/1/accept"), ("delete", "/teacher/invitations/1"),
    ],
)
async def test_teacher_endpoints_are_for_teachers_only(client, people, method, path):
    assert (await getattr(client, method)(path)).status_code == 401
    assert (await getattr(client, method)(path, headers=people["s1"])).status_code == 403


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/me/teachers"), ("post", "/me/teachers/requests"), ("post", "/me/invitations/1/accept"),
        ("post", "/me/invitations/1/decline"), ("delete", "/me/requests/1"), ("delete", "/me/teachers/x"),
    ],
)
async def test_student_link_endpoints_are_for_students_only(client, people, method, path):
    assert (await getattr(client, method)(path)).status_code == 401
    assert (await getattr(client, method)(path, headers=people["t1"])).status_code == 403


async def test_idor_on_invitations_requests_and_groups(client, db, people):
    gid = await group(client, people["t1"], "Mine")
    other_gid = await group(client, people["t2"], "Theirs")
    await invite(client, people["t1"], "stud_one", gid)
    invitation = (await my_teachers(client, people["s1"]))["invitations"][0]["id"]
    assert (await client.post(f"/me/invitations/{invitation}/accept", headers=people["s2"])).status_code == 404
    assert (await client.post(f"/me/invitations/{invitation}/decline", headers=people["s2"])).status_code == 404
    assert (await client.delete(f"/teacher/invitations/{invitation}", headers=people["t2"])).status_code == 404
    assert (await client.delete(f"/me/requests/{invitation}", headers=people["s1"])).status_code == 404

    await ask(client, people["s2"], "teach_one")
    request = (await teacher_links(client, people["t1"]))["requests"][0]["id"]
    assert (await client.post(f"/teacher/requests/{request}/accept", headers=people["t2"], json={})).status_code == 404
    assert (await client.post(f"/teacher/requests/{request}/decline", headers=people["t2"])).status_code == 404
    assert (await client.delete(f"/me/requests/{request}", headers=people["s1"])).status_code == 404
    assert (await client.post(f"/teacher/requests/{request}/accept", headers=people["t1"], json={"group_id": other_gid})).status_code == 404
    assert not await linked(db, "teach_one", "stud_two")

    assert (await client.put(f"/teacher/groups/{gid}", headers=people["t2"], json={"name": "Hacked"})).status_code == 404
    assert (await client.delete(f"/teacher/groups/{gid}", headers=people["t2"])).status_code == 404
    assert (await invite(client, people["t2"], "stud_one", gid)).status_code == 404
    assert await db.scalar(select(TeacherGroup.name).where(TeacherGroup.id == gid)) == "Mine"


async def test_idor_on_links_between_other_people(client, db, people):
    await invite(client, people["t1"], "stud_one")
    request_id = (await my_teachers(client, people["s1"]))["invitations"][0]["id"]
    await client.post(f"/me/invitations/{request_id}/accept", headers=people["s1"])
    gid = await group(client, people["t2"], "Other")
    assert (await client.delete("/teacher/students/stud_one", headers=people["t2"])).status_code == 404
    assert (await client.put("/teacher/students/stud_one/group", headers=people["t2"], json={"group_id": gid})).status_code == 404
    assert (await client.delete("/me/teachers/teach_one", headers=people["s2"])).status_code == 404
    assert (await client.delete("/me/teachers/teach_two", headers=people["s1"])).status_code == 404
    assert await linked(db, "teach_one", "stud_one")
    assert (await client.put("/teacher/students/stud_one/group", headers=people["t1"], json={"group_id": gid})).status_code == 404
