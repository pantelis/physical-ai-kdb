import pdfplumber
import pytest
from conftest import make_pdf

from paiw_tools.locate import find_quote, norm

LEFT = [(72, 700, "The first half of"), (72, 686, "the sentence ends.")]
RIGHT = [(320, 700, "Other text here"), (320, 686, "more right text")]
WRAPPED = [(72, 600, "a robust manip-"), (72, 586, "ulation policy.")]
TWICE = [(72, 500, "Success was 76.5 here."), (72, 400, "And 76.5 again.")]


@pytest.fixture
def page(tmp_path):
    pdf = tmp_path / "p.pdf"
    boxes = make_pdf(pdf, [LEFT + RIGHT + WRAPPED + TWICE])
    with pdfplumber.open(pdf) as doc:
        yield doc.pages[0], boxes


def close(a, b, tol=1.5):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_a_one_line_quote_is_found_at_its_position(page):
    p, boxes = page
    [span] = find_quote(p, "Other text here")
    assert close(span[::2], boxes["Other text here"][::2])  # x0, x1
    assert boxes["Other text here"][1] - 1 <= span[1] < span[3] <= boxes["Other text here"][3] + 1


def test_a_sentence_in_one_column_is_found_even_when_page_text_interleaves_columns(page):
    p, boxes = page
    assert "The first half of the sentence ends." not in " ".join((p.extract_text() or "").split())
    [span] = find_quote(p, "The first half of the sentence ends.")
    assert span[1] <= boxes["the sentence ends."][1] + 1 and span[3] >= boxes["The first half of"][3] - 1


def test_a_hyphen_that_breaks_a_word_across_lines_is_ignored(page):
    p, _ = page
    assert len(find_quote(p, "a robust manipulation policy.")) == 1


def test_quotes_and_dashes_and_spacing_are_normalized(page):
    p, _ = page
    assert len(find_quote(p, "Other   text\nhere")) == 1


def test_text_that_is_not_on_the_page_gives_no_spans(page):
    p, _ = page
    assert find_quote(p, "OpenVLA is trained on one million episodes.") == []
    assert find_quote(p, "") == []


def test_every_occurrence_is_returned(page):
    p, boxes = page
    spans = find_quote(p, "76.5")
    assert len(spans) == 2
    assert spans[0][1] > spans[1][1]  # the first one is higher on the page


def test_ligatures_curly_quotes_and_dashes_compare_equal():
    assert norm("ﬁne-tuned “policy” – robot") == norm('fine-tuned "policy" - robot')


MIDLINE = [(72, 300, "Before text. The quote starts"), (72, 286, "here and ends. After it.")]


@pytest.fixture
def midline(tmp_path):
    pdf = tmp_path / "m.pdf"
    boxes = make_pdf(pdf, [MIDLINE])
    with pdfplumber.open(pdf) as doc:
        yield doc.pages[0], boxes


def test_a_quote_over_two_lines_gets_one_box_per_line(midline):
    from paiw_tools.locate import find_quote_lines
    p, boxes = midline
    [lines] = find_quote_lines(p, "The quote starts here and ends.")
    assert len(lines) == 2
    first, second = lines
    assert first[0] > boxes["Before text. The quote starts"][0] + 20  # starts after "Before text. "
    assert second[2] < boxes["here and ends. After it."][2] - 20      # ends before " After it."
    assert first[1] > second[1]                                       # the first line is higher


def test_the_line_boxes_span_the_same_area_as_the_quote_bbox(midline):
    from paiw_tools.locate import find_quote_lines
    p, _ = midline
    [span] = find_quote(p, "The quote starts here and ends.")
    [lines] = find_quote_lines(p, "The quote starts here and ends.")
    union = [min(b[0] for b in lines), min(b[1] for b in lines), max(b[2] for b in lines), max(b[3] for b in lines)]
    assert union == span
