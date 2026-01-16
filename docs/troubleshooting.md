# news-watch Troubleshooting Guide

This guide covers common issues specific to news-watch and how to resolve them.

## Installation Issues

### Playwright Installation Problems

**Problem**: `playwright install chromium` fails or browser not found errors.

**Solutions**:
```bash
# Install playwright browser for news-watch
conda activate newswatch-env
playwright install chromium

# For system dependencies
playwright install-deps chromium

# For Docker/Linux environments
apt-get update && apt-get install -y \
    libnss3 libatk-bridge2.0-0 libdrm2 libxcomposite1 \
    libxdamage1 libxrandr2 libgbm1 libxss1 libasound2
```

### news-watch Installation Issues

**Problem**: Package installation fails or import errors.

**Solutions**:
```bash
# Use uv pip as recommended for news-watch
conda activate newswatch-env
uv pip install -r requirements.txt

# For development
uv pip install -r requirements-dev.txt

# If uv is not available, fallback to pip
pip install news-watch
```

## Runtime Issues

### No Articles Found

**Problem**: Scraping returns empty results even though articles should exist.

**Diagnostic steps**:
```bash
# Using CLI with verbose output
newswatch --keywords test --start_date 2025-01-01 -v

# Check available scrapers
newswatch --list_scrapers

# Test with common Indonesian keyword
newswatch --keywords indonesia --start_date 2025-01-15 -v
```

**Common causes and fixes**:

1. **Keywords too specific**: Use broader, more common Indonesian terms
   ```bash
   # Instead of very specific terms
   newswatch --keywords "very-specific-company-name" --start_date 2025-01-01
   
   # Try broader categories
   newswatch --keywords "ekonomi,bisnis" --start_date 2025-01-01
   ```

2. **Date range too far back**: Some scrapers have limited archives
   ```bash
   # Instead of very old dates
   newswatch --keywords politik --start_date 2020-01-01
   
   # Try recent dates first
   newswatch --keywords politik --start_date 2025-01-01
   ```

3. **Platform-specific scraper issues**: Let news-watch choose appropriate scrapers
   ```bash
   # Use specific working scrapers instead of all
   newswatch --keywords berita --start_date 2025-01-01 --scrapers "kompas,detik,tempo"
   ```

### Timeout Errors

**Problem**: Scraping times out before completing.

**Solutions**:
```bash
# Use smaller date ranges to avoid timeouts
newswatch --keywords politik --start_date 2025-01-01 --end_date 2025-01-07

# Use fewer scrapers to reduce load
newswatch --keywords politik --start_date 2025-01-01 --scrapers "kompas,detik"

# Use output file instead of keeping in memory
newswatch --keywords politik --start_date 2025-01-01 --output_format xlsx

# Use JSON for smaller file size and API integration
newswatch --keywords politik --start_date 2025-01-01 --output_format json
```

### Memory Issues

**Problem**: Out of memory errors when scraping large amounts of data.

**Solutions**:
```bash
# Always save to file for large datasets
newswatch --keywords ekonomi --start_date 2024-01-01 --output_format xlsx

# Use JSON for more efficient storage of large datasets
newswatch --keywords ekonomi --start_date 2024-01-01 --output_format json

# Use smaller date ranges
newswatch --keywords ekonomi --start_date 2025-01-01 --end_date 2025-01-07

# Use fewer scrapers to reduce memory usage
newswatch --keywords ekonomi --start_date 2025-01-01 --scrapers "kompas,detik"
```

## Platform-Specific Issues

### Linux Performance Problems

**Problem**: Some scrapers fail or perform poorly on Linux.

**Causes**: Anti-bot measures often target cloud/server environments.

**Solutions**:
```bash
# news-watch automatically excludes problematic scrapers on Linux
newswatch --keywords berita --start_date 2025-01-01

# Or manually specify known working scrapers
newswatch --keywords berita --start_date 2025-01-01 --scrapers "kompas,detik,bisnis,tempo"
```

### Cloud Environment Issues

**Problem**: High failure rates or IP blocking in cloud environments like Google Colab.

**Understanding**: Cloud platforms often have shared IPs that news sites block.

**Solutions**:
```bash
# Use fewer scrapers to reduce detection
newswatch --keywords berita --start_date 2025-01-01 --scrapers "kompas,detik"

# Use smaller date ranges
newswatch --keywords politik --start_date 2025-01-15 --end_date 2025-01-16

# Consider running locally if cloud environment fails consistently
```

## Data Quality Issues

### Incomplete Article Content

**Problem**: Some articles have missing or truncated content.

**Causes**: 
- Website changes their HTML structure
- Paywall or subscription content
- Anti-scraping measures

**Diagnostics**:
```bash
# Run with verbose output to see scraping issues
newswatch --keywords ekonomi --start_date 2025-01-01 -v

# Check which scrapers are having issues by testing individually
newswatch --keywords ekonomi --start_date 2025-01-01 --scrapers kompas -v
newswatch --keywords ekonomi --start_date 2025-01-01 --scrapers detik -v
```

### Duplicate Articles

**Problem**: Same article appears multiple times across different sources.

**Understanding**: This is normal behavior when multiple news sites cover the same story. news-watch doesn't automatically deduplicate because users may want to see coverage differences.

**Note**: Post-processing deduplication should be done in your analysis workflow if needed.

### Encoding Issues

**Problem**: Strange characters in article text.

**Understanding**: This can happen due to website encoding issues or character set problems.

**Solutions**:
```bash
# Try different scrapers if one source has encoding issues
newswatch --keywords berita --start_date 2025-01-01 --scrapers "kompas,tempo" -v

# The verbose flag will show which sources have problems
```

## CLI and Command Issues

### Command Not Found

**Problem**: `newswatch` command not recognized.

**Solutions**:
```bash
# Activate the correct conda environment
conda activate newswatch-env

# Check if news-watch is installed
which newswatch

# If not found, reinstall
uv pip install -e .
```

### Invalid Arguments

**Problem**: CLI arguments not working as expected.

**Solutions**:
```bash
# Check command syntax
newswatch --help

# Common patterns:
newswatch --keywords "term1,term2" --start_date 2025-01-01
newswatch -k politik -s "kompas,detik" --output_format xlsx -v
newswatch -k politik -s "kompas,detik" --output_format json -v  # JSON alternative
```

## Testing Issues

### Test Failures

**Problem**: pytest tests fail when running development tests.

**Solutions**:
```bash
# Run tests with proper environment
conda activate newswatch-env

# Run all tests
pytest tests/

# Run only network tests
pytest -m network

# Run specific scraper tests
pytest tests/test_scrapers.py -v

# Skip network tests if offline
pytest -m "not network"
```

## Getting Help

### Diagnostic Information to Collect

When reporting issues, include:

```bash
# System and environment information
echo "Platform: $(uname -a)"
echo "Python version: $(python --version)"
conda list | grep news-watch

# Test basic functionality
newswatch --list_scrapers
newswatch --keywords indonesia --start_date 2025-01-15 -v
```

### Where to Get Help

1. **Check this troubleshooting guide** for common solutions
2. **Search existing issues** on [GitHub Issues](https://github.com/okkymabruri/news-watch/issues)
3. **Create a new issue** with:
   - Complete error messages
   - Your system information (from diagnostic script above)
   - Minimal command that reproduces the problem
   - What you expected vs. what happened

Remember: news-watch is actively developed, and many issues have simple solutions. Don't hesitate to ask for help!