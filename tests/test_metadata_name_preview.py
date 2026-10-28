"""Selected-field preview is an in-memory name projection, never an export writer."""
import copy
import json
import unittest

from defiantmaple import metadata


class MetadataNamePreviewTests(unittest.TestCase):
    def snapshot(self):
        return {"asset_id": "captured-id", "tags": [{"name": "Fictional tag", "aliases": ["omit alias"]}],
                "entities": [{"entity_type": kind, "name": f"Fictional {kind}",
                              "entity_id": "omit-id", "aliases": ["omit alias"]}
                             for kind in metadata.ENTITY_TYPES],
                "prompt": "omit prompt", "source_path": "omit path", "rating": 5}

    def test_all_fields_off_and_explicit_sensitive_inclusion(self):
        value = self.snapshot()
        self.assertEqual(metadata.preview_metadata_names(value), {})
        selected = metadata.preview_metadata_names(value, ("tags", "Artist"))
        self.assertEqual(selected, {"tags": ["Fictional tag"], "Artist": ["Fictional Artist"]})
        text = json.dumps(selected)
        for omitted in ("Fictional Location", "Fictional Client", "omit", "captured-id", "rating"):
            self.assertNotIn(omitted, text)
        self.assertEqual(metadata.preview_metadata_names(value, ("Location", "Client")),
                         {"Location": ["Fictional Location"], "Client": ["Fictional Client"]})

    def test_no_mutation_and_no_shared_output_lists(self):
        value = self.snapshot()
        before = copy.deepcopy(value)
        output = metadata.preview_metadata_names(value, ("tags",))
        output["tags"].append("changed preview")
        self.assertEqual(value, before)

    def test_unknown_duplicate_fields_and_malformed_data_refuse(self):
        for fields in (("prompt",), ("tags", "tags"), "tags", (True,)):
            with self.assertRaises(ValueError):
                metadata.preview_metadata_names(self.snapshot(), fields)
        value = self.snapshot()
        value["entities"][0]["entity_type"] = "Unexpected"
        with self.assertRaises(ValueError):
            metadata.preview_metadata_names(value)

    def test_count_and_text_bounds_refuse_even_when_omitted(self):
        value = self.snapshot()
        value["tags"] = [{"name": "label"}] * 257
        with self.assertRaisesRegex(ValueError, "256"):
            metadata.preview_metadata_names(value)
        value = self.snapshot()
        value["tags"] = [{"name": "é" * 32768}]
        with self.assertRaisesRegex(ValueError, "64 KiB"):
            metadata.preview_metadata_names(value)


if __name__ == "__main__":
    unittest.main()
