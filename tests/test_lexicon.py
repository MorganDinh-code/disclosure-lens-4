from disclosure_lens import lexicon

CSV = ("Word,Seq_num,Word Count,Negative,Positive,Uncertainty,Litigious,Strong_Modal,Weak_Modal,Constraining\n"
       "LOSS,1,10,2009,0,0,0,0,0,0\nGOOD,2,10,0,2009,0,0,0,0,0\nMAYBE,3,10,0,0,2009,0,0,2009,0\n"
       "WILL,4,10,0,0,0,0,2009,0,0\nLAWSUIT,5,10,2009,0,0,2009,0,0,0\nPLAIN,6,10,0,0,0,0,0,0,0\n")


def test_load_and_tone(tmp_path):
    (tmp_path / "X_MasterDictionary_test.csv").write_text(CSV)
    lexicon.load.cache_clear()
    d = lexicon.load(str(tmp_path))
    assert d["n_words"] == 6 and "maybe" in d["cats"]["uncertainty"]
    pos, neg = lexicon.words("positive", str(tmp_path)), lexicon.words("negative", str(tmp_path))
    assert lexicon.tone_counts(["good"], pos, neg) == (1, 0)
    assert lexicon.tone_counts(["not", "very", "good"], pos, neg) == (0, 1)  # negated positive
    assert lexicon.lookup("lawsuit", str(tmp_path)) == {"Negative": 2009, "Litigious": 2009}
