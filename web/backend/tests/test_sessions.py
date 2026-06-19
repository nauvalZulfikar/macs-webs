"""Tests for get_chat_count in sessions.py."""
import pytest
import sessions


# ---------------------------------------------------------------------------
# get_chat_count
# ---------------------------------------------------------------------------

class TestGetChatCountMissingDir:
    """Returns 0 when the chats directory does not exist."""

    def test_returns_zero_when_project_path_has_no_macs_dir(self, tmp_path):
        # Arrange: project dir exists but has no .macs/ subtree
        project = tmp_path / "myproject"
        project.mkdir()

        # Act
        result = sessions.get_chat_count(str(project))

        # Assert
        assert result == 0

    def test_returns_zero_when_macs_dir_exists_but_no_chats_subdir(self, tmp_path):
        # Arrange
        project = tmp_path / "myproject"
        (project / ".macs").mkdir(parents=True)

        # Act
        result = sessions.get_chat_count(str(project))

        # Assert
        assert result == 0

    def test_returns_zero_when_chats_dir_exists_but_is_empty(self, tmp_path):
        # Arrange
        project = tmp_path / "myproject"
        (project / ".macs" / "chats").mkdir(parents=True)

        # Act
        result = sessions.get_chat_count(str(project))

        # Assert
        assert result == 0


class TestGetChatCountMdFiles:
    """Counts only .md files directly inside chats/."""

    def test_counts_single_md_file(self, tmp_path):
        # Arrange
        chats = tmp_path / ".macs" / "chats"
        chats.mkdir(parents=True)
        (chats / "handover-001.md").write_text("# Chat 1")

        # Act
        result = sessions.get_chat_count(str(tmp_path))

        # Assert
        assert result == 1

    def test_counts_multiple_md_files(self, tmp_path):
        # Arrange
        chats = tmp_path / ".macs" / "chats"
        chats.mkdir(parents=True)
        for i in range(4):
            (chats / f"handover-{i:03d}.md").write_text(f"# Chat {i}")

        # Act
        result = sessions.get_chat_count(str(tmp_path))

        # Assert
        assert result == 4

    def test_does_not_count_non_md_files(self, tmp_path):
        # Arrange
        chats = tmp_path / ".macs" / "chats"
        chats.mkdir(parents=True)
        (chats / "handover-001.md").write_text("# Chat 1")
        (chats / "notes.txt").write_text("some text")
        (chats / "data.json").write_text("{}")

        # Act
        result = sessions.get_chat_count(str(tmp_path))

        # Assert
        assert result == 1

    def test_does_not_recurse_into_subdirectories(self, tmp_path):
        # Arrange
        chats = tmp_path / ".macs" / "chats"
        chats.mkdir(parents=True)
        (chats / "top.md").write_text("# Top-level")
        subdir = chats / "archive"
        subdir.mkdir()
        (subdir / "nested.md").write_text("# Nested — must NOT be counted")

        # Act
        result = sessions.get_chat_count(str(tmp_path))

        # Assert — only the top-level .md counts
        assert result == 1


class TestGetChatCountSymlinks:
    """Symlinks pointing at .md files count; others don't."""

    def test_symlink_to_md_file_counts(self, tmp_path):
        # Arrange
        chats = tmp_path / ".macs" / "chats"
        chats.mkdir(parents=True)
        real_md = tmp_path / "real.md"
        real_md.write_text("# Real")
        link = chats / "link.md"
        link.symlink_to(real_md)

        # Act
        result = sessions.get_chat_count(str(tmp_path))

        # Assert
        assert result == 1

    def test_symlink_without_md_extension_does_not_count(self, tmp_path):
        # Arrange
        chats = tmp_path / ".macs" / "chats"
        chats.mkdir(parents=True)
        real_md = tmp_path / "real.md"
        real_md.write_text("# Real")
        link = chats / "link.txt"          # symlink but not .md extension
        link.symlink_to(real_md)

        # Act
        result = sessions.get_chat_count(str(tmp_path))

        # Assert
        assert result == 0

    def test_symlink_to_directory_does_not_recurse(self, tmp_path):
        # Arrange
        chats = tmp_path / ".macs" / "chats"
        chats.mkdir(parents=True)
        real_dir = tmp_path / "archive"
        real_dir.mkdir()
        (real_dir / "nested.md").write_text("# Nested")
        link = chats / "archive_link"
        link.symlink_to(real_dir)          # symlink → directory

        # Act
        result = sessions.get_chat_count(str(tmp_path))

        # Assert — symlink to dir must NOT recurse
        assert result == 0
