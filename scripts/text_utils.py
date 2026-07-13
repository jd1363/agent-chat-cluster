"""Text utility functions for generating URL-friendly slugs."""

import re


def slugify(text: str) -> str:
    """Convert a string into a URL-friendly slug.

    Transformations applied:
        - Lowercase the input.
        - Replace spaces and underscores with hyphens.
        - Remove characters that are not alphanumeric or hyphens.
        - Collapse consecutive hyphens into a single hyphen.
        - Strip leading and trailing hyphens.

    Args:
        text: The raw input string.

    Returns:
        A cleaned, URL-friendly slug.
    """
    # Lowercase and replace spaces/underscores with hyphens
    slug = text.lower().replace(" ", "-").replace("_", "-")
    # Remove any character that is not a letter, number, or hyphen
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    # Collapse multiple consecutive hyphens
    slug = re.sub(r"-+", "-", slug)
    # Strip leading and trailing hyphens
    slug = slug.strip("-")
    return slug


if __name__ == "__main__":
    test_cases = [
        ("Hello World", "hello-world"),
        ("This is a test_string!", "this-is-a-test-string"),
        ("---Multiple___Spaces and Symbols!!!---", "multiple-spaces-and-symbols"),
        ("UPPER lower 123", "upper-lower-123"),
        ("__leading_trailing__", "leading-trailing"),
        ("a---b___c", "a-b-c"),
    ]

    all_passed = True
    for raw, expected in test_cases:
        result = slugify(raw)
        status = "PASS" if result == expected else "FAIL"
        if status == "FAIL":
            all_passed = False
        print(f"[{status}] slugify({raw!r}) -> {result!r} (expected {expected!r})")

    print()
    if all_passed:
        print("All tests passed.")
    else:
        print("Some tests failed.")
