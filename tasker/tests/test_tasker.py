"""
Tests for ``tasker.tasker``.
"""

import signal
import tarfile

import pathlib
import psutil

from common.testtools import ROOTFS_URI
from tasker.tasker import _create_filesystem_dir, _run_chroot_process, Task


class TestCreateFilestystemDir(object):
    """
    Tests for ``_create_filesystem_dir``.
    """

    def _create_tarfile(self, tmpdir):
        """
        Create a ``.tar`` file containing ``hello.txt`` when extracted.

        :param tmpdir: The directory in which to create the archive and text
            file.

        :rtype: str
        :return: URI of the tar file.
        """
        text_file = tmpdir.join("hello.txt")
        text_file.write("content")
        tar_file = tmpdir.join('filesystem.tar')
        with tarfile.open(tar_file.strpath, 'w') as tar:
            tar.add(text_file.strpath, arcname=text_file.basename)
        image_url = pathlib.Path(tar_file.strpath).as_uri()
        return image_url

    def test_filesystem_dir_created(self, tmpdir):
        """
        The given ``.tar`` file is downloaded and extracted to the given
        download path.
        """
        image_url = self._create_tarfile(tmpdir=tmpdir.mkdir('server'))

        client = pathlib.Path(tmpdir.mkdir('client').strpath)
        extracted_filesystem = _create_filesystem_dir(
            image_url=image_url,
            download_path=client,
        )

        assert extracted_filesystem.parent == client
        assert extracted_filesystem.joinpath('hello.txt').exists()

    def test_multiple_filesystems(self, tmpdir):
        """
        Multiple filesystem directories can exist from the same image.
        """
        image_url = self._create_tarfile(tmpdir=tmpdir.mkdir('server'))

        client = pathlib.Path(tmpdir.mkdir('client').strpath)
        extracted_filesystem_1 = _create_filesystem_dir(
            image_url=image_url,
            download_path=client,
        )

        extracted_filesystem_2 = _create_filesystem_dir(
            image_url=image_url,
            download_path=client,
        )

        assert extracted_filesystem_1 != extracted_filesystem_2

    def test_image_removed(self, tmpdir):
        """
        The downloaded image is deleted.
        """
        image_url = self._create_tarfile(tmpdir=tmpdir.mkdir('server'))

        client = pathlib.Path(tmpdir.mkdir('client').strpath)
        extracted_filesystem = _create_filesystem_dir(
            image_url=image_url,
            download_path=client,
        )

        client_children = [item for item in client.iterdir()]
        assert client_children == [extracted_filesystem]


class TestRunChrootProcess(object):
    """
    Tests for ``_run_chroot_process``.
    """

    def _create_filesystem_dir(self, tmpdir):
        """
        Return a directory path with an extracted filesystem.
        """
        return _create_filesystem_dir(
            image_url=ROOTFS_URI,
            download_path=pathlib.Path(tmpdir.strpath),
        )

    def test_run_chroot_process(self, tmpdir):
        """
        A new process is created from the given arguments in a chroot jail
        of the given filesystem path.
        """
        filesystem = self._create_filesystem_dir(tmpdir)

        _run_chroot_process(
            filesystem=filesystem,
            args=['touch', '/example.txt'],
        )

        assert filesystem.joinpath('example.txt').exists()

    def test_process_returned(self, tmpdir):
        """
        A new process with a new process ID is created, and the process object
        is returned.
        """
        old_pids = psutil.pids()
        process = _run_chroot_process(
            filesystem=self._create_filesystem_dir(tmpdir),
            args=['touch', '/example.txt'],
        )
        new_pids = set(psutil.pids()) - set(old_pids)
        assert process.pid in new_pids

    def test_default_io(self, tmpdir):
        """
        By default there is a pipe to the standard I/O streams.
        """
        process = _run_chroot_process(
            filesystem=self._create_filesystem_dir(tmpdir),
            args=['echo', '1'],
        )

        assert process.stdout.read() == b'1\n'

    def test_custom_stdout(self, tmpdir):
        """
        A given file descriptor can act as stdout.
        """
        stdout_file = tmpdir.join("output.txt")

        with open(stdout_file.strpath, 'w') as f:
            _run_chroot_process(
                filesystem=self._create_filesystem_dir(tmpdir),
                args=['echo', '1'],
                stdout=f,
            )

        assert stdout_file.read() == '1\n'

    def test_custom_stderr(self, tmpdir):
        """
        A given file descriptor can act as stderr.
        """
        stderr_file = tmpdir.join("output.txt")

        with open(stderr_file.strpath, 'w') as f:
            _run_chroot_process(
                filesystem=self._create_filesystem_dir(tmpdir),
                args=['sleep', 'a'],
                stderr=f,
            )

        assert stderr_file.read() == "sleep: invalid number 'a'\n"


class TestTask(object):
    """
    Tests for ``Task``.
    """

    def test_create(self, tmpdir):
        """
        It is possible to create a new process running a given command.
        """
        task = Task(
            image_url=ROOTFS_URI,
            args=['sleep', '5'],
            download_path=pathlib.Path(tmpdir.strpath),
        )

        assert task.get_health() == {'exists': True, 'status': 'sleeping'}

    def test_send_signal(self, tmpdir):
        """
        Sending a ``SIGINT`` signal to ``task.send_signal`` kills the child
        process.
        """
        task = Task(
            image_url=ROOTFS_URI,
            args=['sleep', '5'],
            download_path=pathlib.Path(tmpdir.strpath),
        )
        task.send_signal(signal.SIGINT)
        assert task.get_health() == {'exists': False, 'status': None}

    def test_existing_task(self, tmpdir):
        """
        It is possible to get an existing task by its id.
        """
        task = Task(
            image_url=ROOTFS_URI,
            args=['sleep', '5'],
            download_path=pathlib.Path(tmpdir.strpath),
        )

        other_task = Task(existing_task=task.id)
        # Interrupting one task interrupts the other, so they are the same task
        task.send_signal(signal.SIGINT)
        assert other_task.get_health() == {'exists': False, 'status': None}

    def test_custom_io(self, tmpdir):
        """
        It is possible to create a new process with custom IO.
        """
        stdout_file = tmpdir.join("output.txt")
        stderr_file = tmpdir.join("err.txt")
        with open(stdout_file.strpath, 'w') as stdout:
            with open(stderr_file.strpath, 'w') as stderr:
                Task(
                    image_url=ROOTFS_URI,
                    args=['echo', '1'],
                    download_path=pathlib.Path(tmpdir.strpath),
                    stdout=stdout,
                    stderr=stderr,
                )
                Task(
                    image_url=ROOTFS_URI,
                    args=['sleep', 'a'],
                    download_path=pathlib.Path(tmpdir.strpath),
                    stdout=stdout,
                    stderr=stderr,
                )

        assert stdout_file.read() == '1\n'
        assert stderr_file.read() == "sleep: invalid number 'a'\n"
