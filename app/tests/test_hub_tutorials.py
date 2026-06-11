import unittest
from pathlib import Path

from gui.hub_tutorials import (
    TUTORIAL_TOPICS,
    tutorial_doc_exists,
    tutorial_topic,
    tutorial_topics,
)


EXPECTED_TOPIC_IDS = {
    "getting-started",
    "overview",
    "farm-plan",
    "multi-instance",
    "settings",
    "discord",
    "telegram",
    "api",
    "timers",
    "match-history",
    "remote-control",
    "troubleshooting",
}


class HubTutorialsTests(unittest.TestCase):
    def test_all_expected_topic_ids_exist(self):
        topic_ids = {topic["id"] for topic in TUTORIAL_TOPICS}
        self.assertEqual(topic_ids, EXPECTED_TOPIC_IDS)

    def test_no_duplicate_topic_ids(self):
        topic_ids = [topic["id"] for topic in TUTORIAL_TOPICS]
        self.assertEqual(len(topic_ids), len(set(topic_ids)))

    def test_each_topic_has_summary_and_valid_doc(self):
        for topic in TUTORIAL_TOPICS:
            self.assertTrue(topic["summary"].strip(), msg=f"missing summary: {topic['id']}")
            self.assertTrue(topic["doc"].startswith("docs/tutorials/"), msg=topic["id"])
            self.assertTrue(
                tutorial_doc_exists(topic["doc"]),
                msg=f"missing doc file for {topic['id']}: {topic['doc']}",
            )

    def test_tutorial_topics_returns_copies(self):
        topics = tutorial_topics()
        self.assertEqual(len(topics), len(TUTORIAL_TOPICS))
        topics[0]["title"] = "changed"
        self.assertNotEqual(TUTORIAL_TOPICS[0]["title"], "changed")

    def test_tutorial_topic_lookup(self):
        topic = tutorial_topic("farm-plan")
        self.assertIsNotNone(topic)
        self.assertEqual(topic["tab"], "Farm Plan")
        self.assertIsNone(tutorial_topic("missing-topic"))

    def test_tutorial_index_exists(self):
        self.assertTrue(Path("docs/TUTORIAL.md").exists())


if __name__ == "__main__":
    unittest.main()
