from disclosure_lens.preprocess import split_sentences, parse_document


def test_abbreviations_do_not_split():
    s = split_sentences("Acme Corp. reported sales of $1.2 bn in the U.S. market. Growth was strong.")
    assert len(s) == 2


def test_positions_are_normalized():
    recs = parse_document("One. Two.\n\nThree. Four.")
    assert [round(r["pos_doc"], 2) for r in recs] == [0.25, 0.5, 0.75, 1.0]
