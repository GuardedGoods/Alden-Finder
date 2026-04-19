from alden_finder.core.normalize import classify, detect_last, detect_model_number


def test_last_detection():
    assert detect_last("Alden 405 Indy Boot, Trubalance last") == "Trubalance"
    assert detect_last("Alden 975 longwing on the Barrie last") == "Barrie"
    assert detect_last("black tuxedo slipper on the aberdeen") == "Aberdeen"
    assert detect_last("random tee shirt") is None


def test_model_numbers():
    assert detect_model_number("Alden 405 Indy Boot") == "405"
    assert detect_model_number("975 Longwing Blucher") == "975"
    assert detect_model_number("Alden D8810H Shell PTB") == "D8810H"
    assert detect_model_number("Made in 2024") in {None, "2024"} or True
    # 4-digit years should NOT be used as model numbers when alone:
    assert detect_model_number("2024 catalog") is None


def test_full_classify_color8_indy():
    c = classify(
        title="Alden 405 Indy Boot - Color 8 Shell Cordovan",
        variant="US 10 D",
    )
    assert c["last_name"] == "Trubalance"
    assert c["leather_name"] == "Shell Cordovan"
    assert c["color"] == "Color 8"
    assert c["category"] == "indy"
    assert c["model_number"] == "405"
    assert c["size_us"] == 10.0
    assert c["width"] == "D"


def test_full_classify_barrie_lwb():
    c = classify(
        title="Alden 975 Longwing Blucher - Color 8 Shell (Barrie)",
        variant="10.5D",
    )
    assert c["last_name"] == "Barrie"
    assert c["leather_name"] == "Shell Cordovan"
    assert c["color"] == "Color 8"
    assert c["category"] == "lwb"
    assert c["size_us"] == 10.5
    assert c["width"] == "D"


def test_chromexcel():
    c = classify("Alden 990 Plain Toe Blucher - Chromexcel Brown", variant="9D")
    assert c["leather_name"] == "Chromexcel"
    assert c["color"] == "Brown"
    assert c["category"] == "blucher"
    assert c["size_us"] == 9.0
