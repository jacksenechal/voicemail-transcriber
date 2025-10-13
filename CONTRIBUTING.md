# Contributing to Telegram Voice Transcriber

Thank you for considering contributing! This project welcomes contributions from everyone.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/telegram-voice-transcriber.git`
3. Create a branch: `git checkout -b feature/your-feature-name`
4. Make your changes
5. Run tests: `pytest`
6. Commit your changes: `git commit -m "Description of changes"`
7. Push to your fork: `git push origin feature/your-feature-name`
8. Open a Pull Request

## Development Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your credentials

# Run tests
pytest
```

## Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_voice_detection.py

# Run with coverage
pytest --cov=transcriber
```

## Code Style

- Follow PEP 8 style guidelines
- Use descriptive variable and function names
- Add docstrings to functions
- Keep functions focused and concise
- Add tests for new features

## Pull Request Guidelines

- **Keep PRs focused**: One feature or fix per PR
- **Write clear commit messages**: Describe what and why, not how
- **Add tests**: All new features should include tests
- **Update documentation**: Update README.md if adding features
- **Run tests**: Ensure all tests pass before submitting
- **Check compatibility**: Test with both test and production modes

## Reporting Issues

When reporting issues, please include:

- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs or error messages

## Feature Requests

Feature requests are welcome! Please:

- Check if the feature already exists
- Describe the use case clearly
- Explain why it would be useful
- Consider if it fits the project scope

## Questions?

Open an issue with the `question` label for any questions about the project.

## Code of Conduct

Be respectful and constructive in all interactions. This project follows the principle of treating others as you would like to be treated.
