import requests
from bs4 import BeautifulSoup
import csv
import time
import random
import urllib.parse
from urllib.robotparser import RobotFileParser
import re
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SmartWebScraper:
    def __init__(self, base_url: str, output_file: str = "scraped_data.csv", delay: tuple = (1, 3), respect_robots: bool = True) -> None:
        """
            Initialize the smart web scrapper

            Args:
                base_url (str): Base url of the website to scrape
                output_file (str): The path to output csv file
                delay (tuple): Tuple of (min_delay, max_delay) between requests in seconds
                respect_robots (bool): Whether to respect robots.txt rule
        """
        self.base_url = base_url
        self.output_file = output_file
        self.delay = delay
        self.respect_robots = respect_robots
        self.visited_urls = set()
        self.queue = [base_url]
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        # setup robot parser
        parsed_url = urllib.parse.urlparse(base_url)
        robots_txt_url = f"{parsed_url.scheme}://{parsed_url.netloc}/robots.txt"
        self.robot_parser = RobotFileParser()
        self.robot_parser.set_url(robots_txt_url)
        self.robot_parser_completed = False
        try:
            self.robot_parser.read()
            self.robot_parser_completed = True
        except Exception as e:
            logger.warning(f"Unable to read robots.txt file: {e}")
        
        # lazily initialize selenium
        self.driver = None
        self.tried_selenium = False

        # create output file with columns
        with open(self.output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['URL', 'Content'])

    def initialize_selenium(self) -> bool:
        """ Initiate selenium headless browser if not already initialize """
        if self.driver is not None:
            return True
        
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        try:
            options = Options()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument(f"user-agent={self.headers['User-Agent']}")
            self.driver = webdriver.Chrome(options=options)
            logger.info("Selenium initiated")
            return True
        except Exception as e:
            logger.error(f"Error initializing selenium: {e}")
            return False
        
    def can_fetch(self, url: str) -> bool:
        """ Check if url can be fetched according to robots.txt """
        if not self.respect_robots:
            return True
        
        return self.robot_parser.can_fetch(self.headers['User-Agent'], url)

    def is_same_domain(self, url: str) -> bool:
        """ Check if url is same domain as base url """
        base_url_domain = urllib.parse.urlparse(self.base_url).netloc
        url_domain = urllib.parse.urlparse(url).netloc
        return base_url_domain == url_domain


    def normalize_url(self, url: str) -> str:
        """ Normalize relative to absolute URL """
        if url.startswith('http'):
            return url
        return urllib.parse.urljoin(self.base_url, url)
    
    def detect_javascript_content(self, html_content):
        """
        Detect if the page likely requires JavaScript rendering.
        
        Returns True if the page likely needs JavaScript to load content.
        """
        # Look for common JavaScript frameworks
        js_framework_patterns = [
            r'react', r'vue', r'angular', r'next.js', r'nuxt',
            r'data-react', r'ng-app', r'v-for',
            r'\_\_NEXT_DATA\_\_', r'window.__NUXT__'
        ]
        
        # Look for content that's likely loaded via JS
        js_content_patterns = [
            r'<div id="app">\s*</div>',
            r'<div id="root">\s*</div>',
            r'getElementById\(.+?\)\.innerHTML',
            r'document\.write\(',
            r'display:\s*none;.+?[\'"]initial[\'"]'
        ]
        
        # Check if the body has minimal content (potential JS loading)
        soup = BeautifulSoup(html_content, 'html.parser')
        body = soup.find('body')
        
        if body and len(body.get_text(strip=True)) < 100:
            # Look for specific script tags that suggest client-side rendering
            scripts = soup.find_all('script')
            for script in scripts:
                # Check script content or src attribute
                if script.string:
                    for pattern in js_framework_patterns:
                        if re.search(pattern, script.string, re.I):
                            return True
                if script.get('src'):
                    for pattern in js_framework_patterns:
                        if re.search(pattern, script['src'], re.I):
                            return True
        
        # Check for patterns in the entire HTML
        for pattern in js_framework_patterns + js_content_patterns:
            if re.search(pattern, html_content, re.I):
                return True
                
        return False
    
    def get_page_content(self, url):
        """Get the page content, automatically choosing between requests and Selenium."""
        # First try with regular requests
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                html_content = response.text
                
                # Check if content might need JavaScript rendering
                if self.detect_javascript_content(html_content):
                    logger.info(f"Detected JavaScript-heavy content at {url}, trying Selenium")
                    
                    # Initialize Selenium if not already done
                    if not self.tried_selenium and self.initialize_selenium():
                        self.tried_selenium = True
                        try:
                            self.driver.get(url)
                            time.sleep(3)  # Wait for JavaScript to render
                            return self.driver.page_source
                        except Exception as e:
                            logger.error(f"Selenium error for {url}: {e}")
                            # Fall back to regular requests content
                            return html_content
                    else:
                        logger.warning("Could not initialize Selenium, using regular requests content")
                        return html_content
                else:
                    return html_content
            else:
                logger.warning(f"Failed to fetch {url}: Status code {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Request error for {url}: {e}")
            
            # Try with Selenium as fallback if regular request failed
            if not self.tried_selenium and self.initialize_selenium():
                self.tried_selenium = True
                try:
                    self.driver.get(url)
                    time.sleep(3)  # Wait for JavaScript to render
                    return self.driver.page_source
                except Exception as se:
                    logger.error(f"Selenium fallback error for {url}: {se}")
            
            return None
    
    def extract_text(self, html_content):
        """Extract all text content from HTML."""
        if not html_content:
            return ""
            
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for script_or_style in soup(['script', 'style', 'noscript', 'iframe', 'svg', 'img']):
            script_or_style.decompose()
        
        # Get text and normalize whitespace
        text = soup.get_text(separator=' ')
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def extract_links(self, html_content):
        """Extract all links from HTML content."""
        if not html_content:
            return []
            
        soup = BeautifulSoup(html_content, 'html.parser')
        links = []
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            # Skip anchors, javascript, mailto, etc.
            if href.startswith('#') or href.startswith('javascript:') or href.startswith('mailto:') or href.startswith('tel:'):
                continue
                
            full_url = self.normalize_url(href)
            # Only include links within the same domain
            if self.is_same_domain(full_url):
                links.append(full_url)
        
        return links
    
    def save_to_csv(self, url, content):
        """Append URL and content to the CSV file."""
        with open(self.output_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([url, content])
    
    def scrape(self, max_pages=None):
        """
        Main scraping function.
        
        Args:
            max_pages (int, optional): Maximum number of pages to scrape. None for unlimited.
        """
        page_count = 0
        
        try:
            while self.queue and (max_pages is None or page_count < max_pages):
                # Get the next URL from the queue
                url = self.queue.pop(0)
                
                # Skip if already visited or if robots.txt disallows
                if url in self.visited_urls or (self.robot_parser_completed and not self.can_fetch(url)):
                    continue
                    
                logger.info(f"Scraping {url}")
                self.visited_urls.add(url)
                
                # Add a random delay between requests
                time.sleep(random.uniform(self.delay[0], self.delay[1]))
                
                # Get page content with smart detection
                html_content = self.get_page_content(url)
                if html_content:
                    # Extract text and save to CSV
                    text_content = self.extract_text(html_content)
                    self.save_to_csv(url, text_content)
                    
                    # Extract links and add to queue
                    links = self.extract_links(html_content)
                    for link in links:
                        if link not in self.visited_urls and link not in self.queue:
                            self.queue.append(link)
                
                page_count += 1
                logger.info(f"Completed {page_count} pages. Queue size: {len(self.queue)}")
        
        finally:
            # Clean up Selenium driver if it was used
            if self.driver:
                self.driver.quit()
                logger.info("Selenium WebDriver closed")
            
            logger.info(f"Scraping completed. Scraped {page_count} pages. Data saved to {self.output_file}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Smart web scraper that extracts text content and saves to CSV")
    parser.add_argument("url", help="Base URL of the website to scrape")
    parser.add_argument("--output", "-o", default="scraped_data.csv", help="Output CSV file path")
    parser.add_argument("--max-pages", "-m", type=int, default=None, help="Maximum number of pages to scrape")
    parser.add_argument("--delay-min", type=float, default=1, help="Minimum delay between requests in seconds")
    parser.add_argument("--delay-max", type=float, default=3, help="Maximum delay between requests in seconds")
    parser.add_argument("--ignore-robots", action="store_true", help="Ignore robots.txt rules")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], 
                        help="Set the logging level")
    
    args = parser.parse_args()
    
    # Configure logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    scraper = SmartWebScraper(
        base_url=args.url,
        output_file=args.output,
        delay=(args.delay_min, args.delay_max),
        respect_robots=not args.ignore_robots
    )
    
    scraper.scrape(max_pages=args.max_pages)
