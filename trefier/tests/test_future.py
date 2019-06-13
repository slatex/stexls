import unittest
from trefier.misc import future
from time import sleep, time


class Test_Future(unittest.TestCase):
    def test_join(self):
        begin = time()
        f = future.Future(lambda: sleep(3))
        f.done(lambda r: None)
        f.join()
        self.assertAlmostEqual(time() - begin, 3, 2)

    def test_close(self):
        f = future.Future(lambda: sleep(1.0))
        f.done(lambda r: None)
        f.close()
        exception = None
        try:
            f.done(lambda r: None)
        except Exception as e:
            exception = e
        self.assertIsNotNone(exception)
        f.join()

    def test_catch(self):
        def _task():
            raise Exception("_task")
        f = future.Future(_task)
        r = []
        f.done(lambda _: None, lambda t: r.append(t))
        f.join()
        self.assertEqual(len(r), 1)

    def test_parallel(self):
        def _task(task_i):
            sleep(task_i)
            return task_i

        tasks = [
            future.Future(lambda: _task(1)),
            future.Future(lambda: _task(2)),
            future.Future(lambda: _task(3)),
        ]

        results = []
        for f in tasks:
            f.done(results.append)

        begin = time()
        for f in tasks:
            f.join()
        self.assertAlmostEqual(time() - begin, 3, 2)

        self.assertListEqual(results, [1, 2, 3])

    def test_resolve(self):
        f = future.Future(lambda: 1)
        results = []
        f.done(results.append)
        f.join()
        self.assertListEqual(results, [1])
