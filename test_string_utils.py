"""Автоматичні тести для модуля string_utils."""

from string_utils import is_palindrome, reverse_words


def test_is_palindrome():
    """Звичайний паліндром."""
    assert is_palindrome("level") is True
    assert is_palindrome("abba") is True


def test_is_palindrome_false():
    """Рядок, який не є паліндромом, і врахування регістру."""
    assert is_palindrome("python") is False
    assert is_palindrome("Level") is False


def test_is_palindrome_ukrainian():
    """Перевірка українських символів."""
    assert is_palindrome("око") is True
    assert is_palindrome("мова") is False


def test_is_palindrome_empty():
    """Межовий випадок: порожній рядок."""
    assert is_palindrome("") is True


def test_is_palindrome_single_character():
    """Межовий випадок: один символ."""
    assert is_palindrome("а") is True


def test_reverse_words():
    """Зміна порядку слів без зміни літер у словах."""
    assert reverse_words("Я вивчаю Python") == "Python вивчаю Я"


def test_reverse_words_single_word():
    """Одне слово залишається незмінним."""
    assert reverse_words("Python") == "Python"


def test_reverse_words_empty():
    """Порожній рядок і рядок лише з пробілів."""
    assert reverse_words("") == ""
    assert reverse_words("   ") == ""


def test_reverse_words_whitespace():
    """Зайві пробіли, табуляція та перенесення рядка."""
    assert reverse_words("  один   два  ") == "два один"
    assert reverse_words("один\tдва\nтри") == "три два один"