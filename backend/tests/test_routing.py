from app.services.agent_router import route_intent, detect_artifact_type

def test_route_chat_default():
    assert route_intent("How do I improve retention?") == "chat"

def test_route_ship30_triggers():
    assert route_intent("Write me a ship 30 for 30 essay about onboarding") == "ship30"
    assert route_intent("atomic essay on PLG pricing") == "ship30"
    assert route_intent("Make an essay 1250 words") == "ship30"

def test_route_artifact_triggers():
    assert route_intent("Create an artifact for this") == "artifact"
    assert route_intent("render an HTML one-pager") == "artifact"
    assert route_intent("markdown doc comparing PLG vs sales-led") == "artifact"

def test_route_explicit_mode_wins():
    assert route_intent("anything", requested_mode="ship30") == "ship30"
    assert route_intent("anything ship 30", requested_mode="chat") == "chat"

def test_detect_artifact_type():
    assert detect_artifact_type("make html artifact") == "html"
    assert detect_artifact_type("markdown doc") == "markdown"
    assert detect_artifact_type("anything", explicit="html") == "html"
    assert detect_artifact_type("no hint") == "html"  # default
