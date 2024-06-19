from django.test import TestCase


class test_demo(TestCase):
	def test_plus(self):
		a = 1
		b = 2

		self.assertEqual(a + b, 3)
