"""Tests for get_chat_count and get_chat_total_bytes in sessions.py."""
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


# ---------------------------------------------------------------------------
# get_chat_total_bytes
# ---------------------------------------------------------------------------

class TestGetChatTotalBytesMissingDir:
    """Returns 0 when the chats directory does not exist or has no .md files."""

    def test_returns_zero_when_project_path_has_no_macs_dir(self, tmp_path):
        # Arrange: project dir exists but has no .macs/ subtree
        project = tmp_path / "myproject"
        project.mkdir()

        # Act
        result = sessions.get_chat_total_bytes(str(project))

        # Assert
        assert result == 0

    def test_returns_zero_when_macs_dir_exists_but_no_chats_subdir(self, tmp_path):
        # Arrange
        project = tmp_path / "myproject"
        (project / ".macs").mkdir(parents=True)

        # Act
        result = sessions.get_chat_total_bytes(str(project))

        # Assert
        assert result == 0

    def test_returns_zero_when_chats_dir_is_empty(self, tmp_path):
        # Arrange
        project = tmp_path / "myproject"
        (project / ".macs" / "chats").mkdir(parents=True)

        # Act
        result = sessions.get_chat_total_bytes(str(project))

        # Assert
        assert result == 0

    def test_returns_zero_when_chats_dir_has_no_md_files(self, tmp_path):
        # Arrange
        chats = tmp_path / ".macs" / "chats"
        chats.mkdir(parents=True)
        (chats / "notes.txt").write_text("some text")
        (chats / "data.json").write_bytes(b'{}')

        # Act
        result = sessions.get_chat_total_bytes(str(tmp_path))

        # Assert
        assert result == 0


class TestGetChatTotalBytesSize:
    """Correctly sums byte sizes of .md files."""

    def test_single_md_file_exact_byte_count(self, tmp_path):
        # Arrange
        chats = tmp_path / ".macs" / "chats"
        chats.mkdir(parents=True)
        content = b"hello world"
        (chats / "chat.md").write_bytes(content)

        # Act
        result = sessions.get_chat_total_bytes(str(tmp_path))

        # Assert
        assert result == len(content)

    def test_multiple_md_files_sum_of_sizes(self, tmp_path):
        # Arrange
        chats = tmp_path / ".macs" / "chats"
        chats.mkdir(parents=True)
        (chats / "a.md").write_bytes(b"aaa")       # 3 bytes
        (chats / "b.md").write_bytes(b"bbbbb")     # 5 bytes
        (chats / "c.md").write_bytes(b"cc")        # 2 bytes

        # Act
        result = sessions.get_chat_total_bytes(str(tmp_path))

        # Assert
        assert result == 10

    def test_ignores_non_md_files_in_size_sum(self, tmp_path):
        # Arrange
        chats = tmp_path / ".macs" / "chats"
        chats.mkdir(parents=True)
        (chats / "chat.md").write_bytes(b"abc")    # 3 bytes — counted
        (chats / "notes.txt").write_bytes(b"x" * 100)  # 100 bytes — ignored

        # Act
        result = sessions.get_chat_total_bytes(str(tmp_path))

        # Assert
        assert result == 3

    def test_does_not_recurse_into_subdirectories(self, tmp_path):
        # Arrange
        chats = tmp_path / ".macs" / "chats"
        chats.mkdir(parents=True)
        (chats / "top.md").write_bytes(b"top")     # 3 bytes — counted
        subdir = chats / "archive"
        subdir.mkdir()
        (subdir / "nested.md").write_bytes(b"x" * 50)  # nested — NOT counted

        # Act
        result = sessions.get_chat_total_bytes(str(tmp_path))

        # Assert
        assert result == 3

    def test_empty_md_file_contributes_zero_bytes(self, tmp_path):
        # Arrange
        chats = tmp_path / ".macs" / "chats"
        chats.mkdir(parents=True)
        (chats / "empty.md").write_bytes(b"")

        # Act
        result = sessions.get_chat_total_bytes(str(tmp_path))

        # Assert
        assert result == 0


class TestGetChatTotalBytesSymlinks:
    """Symlinks are followed (target size), not measured by symlink's own size."""

    def test_symlink_to_md_file_counts_target_size(self, tmp_path):
        # Arrange
        chats = tmp_path / ".macs" / "chats"
        chats.mkdir(parents=True)
        real_md = tmp_path / "real.md"
        real_md.write_bytes(b"x" * 42)
        link = chats / "link.md"
        link.symlink_to(real_md)

        # Act
        result = sessions.get_chat_total_bytes(str(tmp_path))

        # Assert — target size (42), not symlink metadata size
        assert result == 42

    def test_symlink_without_md_extension_not_counted(self, tmp_path):
        # Arrange
        chats = tmp_path / ".macs" / "chats"
        chats.mkdir(parents=True)
        real_md = tmp_path / "real.md"
        real_md.write_bytes(b"x" * 10)
        link = chats / "link.txt"   # .txt symlink — must be ignored
        link.symlink_to(real_md)

        # Act
        result = sessions.get_chat_total_bytes(str(tmp_path))

        # Assert
        assert result == 0

    def test_symlink_to_directory_does_not_recurse(self, tmp_path):
        # Arrange
        chats = tmp_path / ".macs" / "chats"
        chats.mkdir(parents=True)
        real_dir = tmp_path / "archive"
        real_dir.mkdir()
        (real_dir / "nested.md").write_bytes(b"y" * 20)
        link = chats / "archive_link"
        link.symlink_to(real_dir)   # symlink → dir — must NOT recurse

        # Act
        result = sessions.get_chat_total_bytes(str(tmp_path))

        # Assert
        assert result == 0
