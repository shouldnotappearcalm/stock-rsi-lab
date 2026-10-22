import unittest
from scripts.continue_asset_expansion_2026_metadata import remaining_scope


class MetadataContinuationScopeTests(unittest.TestCase):
    def test_successes_are_reused_and_only_failed_or_unattempted_sources_are_requested(self):
        cohort=['a','b','c','d'];cases={'a':{'status':'METADATA_CAPTURED_WITH_CANDIDATES'},
            'b':{'status':'METADATA_SOURCE_REJECTED'},'c':{'status':'METADATA_CAPTURED_NO_FULL_CANDIDATE'}}
        reused,todo,retries=remaining_scope(cohort,cases)
        self.assertEqual(list(reused),['a','c']);self.assertEqual(todo,['b','d']);self.assertEqual(retries,['b'])
        self.assertEqual(list(cases),['a','b','c'])

    def test_unknown_status_or_case_outside_frozen_cohort_fails(self):
        for cases in ({'b':{'status':'METADATA_SOURCE_REJECTED'}},{'a':{'status':'UNKNOWN'}}):
            with self.subTest(cases),self.assertRaises(ValueError):remaining_scope(['a'],cases)


if __name__=='__main__':unittest.main()
