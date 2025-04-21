# Smart Web Scraper
A python web scraper with intelligent content extraction capabilities that auto adapt to different web technologies

## Features
- Automatically choose between selenium and requests based on web content
- Can handle javascript rendered websites like React, Next, Vue...
- Recursively crawls all links in the same domain
- Optional respects for robots.txt compliance
- Detailed logs for monitoring and debugging
- Output to csv file

## Installation

### Requirements
- Python 3.7+
- Chrome/chromium browser (for selenium if javascript content is detected)  

### Install Dependencies
Install required packages with `pip3 install -r requirements.txt`

### Clone the repo
- `git clone https://github.com/creativenux/smart-web-scraper.git`
- Change directory using - `cd smart-web-scrapper`
- Or download the `smart_web_scraper.py` file

## Usage

### Basic Usage
`python smart_web_scraper.py https://example.com`

This will:
- Starting scraping the provided url
- Detect if javascript rendering is needed
- Crawl all link within same domain
- Save all extracted text content to `scraped_data.csv`

### Use as a Library
```
from smart_web_scraper import SmartWebScraper

scraper = SmartWebScraper(
    base_url="https://example.com",
    output_file="output.csv",
    delay=(2, 5),
    respect_robots=True
)

scraper.scrape()
```