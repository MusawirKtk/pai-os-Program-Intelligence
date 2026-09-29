"""Canonical IDs keep page aliases together without merging separate programs."""

import unittest

from pai_program_intelligence.dedupe import program_id
from pai_program_intelligence.schemas import Institution, ProgramDetails


class DedupeTests(unittest.TestCase):
    def test_page_aliases_share_id_but_campus_and_code_do_not(self):
        institution = Institution("uni-1", "Example University", "GB", official_url="https://example.edu")
        main = ProgramDetails("MSc Artificial Intelligence", "https://example.edu/program/ai", award="MSc", campus="Main")
        faculty = ProgramDetails("MSc: Artificial Intelligence", "https://example.edu/faculty/ai", award="MSc", campus="Main")
        other_campus = ProgramDetails("MSc Artificial Intelligence", "https://example.edu/program/ai-north", award="MSc", campus="North")
        self.assertEqual(program_id(institution, main), program_id(institution, faculty))
        self.assertNotEqual(program_id(institution, main), program_id(institution, other_campus))
        self.assertNotEqual(program_id(institution, main, program_code="AI-101"), program_id(institution, main, program_code="AI-102"))


if __name__ == "__main__":
    unittest.main()
