# app.py - Fixed Universal E-commerce Product Scraper with Better Encoding
import os
from flask import Flask, request, jsonify, render_template, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import time
import re
import csv
import io
import uuid
from datetime import datetime
from urllib.parse import urljoin, urlparse
import threading
import logging
import random

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///products.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
CORS(app)

# Database Models
class ScrapingJob(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    status = db.Column(db.String(20), default='pending')
    total_urls = db.Column(db.Integer, default=0)
    completed_urls = db.Column(db.Integer, default=0)
    failed_urls = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    current_url = db.Column(db.String(500))
    error_message = db.Column(db.Text)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(36), db.ForeignKey('scraping_job.id'))
    title = db.Column(db.String(500))
    price = db.Column(db.String(50))
    description = db.Column(db.Text)
    part_number = db.Column(db.String(100))
    ean = db.Column(db.String(50))
    brand = db.Column(db.String(100))
    color = db.Column(db.String(50))
    condition = db.Column(db.String(50))
    image_url = db.Column(db.String(500))
    additional_images = db.Column(db.Text)
    source_url = db.Column(db.String(500))
    features = db.Column(db.Text)
    availability = db.Column(db.String(100))
    scraped_at = db.Column(db.DateTime, default=datetime.utcnow)

class UniversalProductScraper:
    def __init__(self, delay=3):
        self.delay = delay
        self.session = requests.Session()
        
        # More realistic browser headers to avoid blocking
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-GB,en;q=0.9,en-US;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        })
    
    def scrape_product(self, url):
        """Universal product scraper with better encoding handling"""
        try:
            logger.info(f"Universal scraping: {url}")
            
            # Random delay to appear more human
            delay = random.uniform(self.delay, self.delay + 2)
            time.sleep(delay)
            
            response = self.session.get(url, timeout=20, allow_redirects=True)
            response.raise_for_status()
            
            # Fix encoding issues
            response.encoding = response.apparent_encoding or 'utf-8'
            
            soup = BeautifulSoup(response.content, 'html.parser', from_encoding='utf-8')
            product_data = self.extract_product_data(soup, url)
            
            # Longer delay after successful scrape
            time.sleep(random.uniform(2, 5))
            return product_data
            
        except Exception as e:
            logger.error(f"Error scraping {url}: {str(e)}")
            return None

    def extract_product_data(self, soup, url):
        """Fixed extraction with better encoding and debug info"""
        product = {'source_url': url}
        
        # Get page text with better encoding handling
        try:
            page_text = soup.get_text(separator=' ', strip=True)
        except:
            page_text = str(soup.get_text())
        
        # Clean up encoding issues
        page_text = page_text.encode('utf-8', errors='ignore').decode('utf-8')
        
        logger.info(f"=== DEBUG INFO FOR {url} ===")
        logger.info(f"Page text length: {len(page_text)}")
        logger.info(f"First 500 chars: {repr(page_text[:500])}")
        
        # TITLE EXTRACTION - Multiple methods
        title = None
        
        # Method 1: Page title tag
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text(strip=True)
            logger.info(f"Found title tag: {repr(title)}")
        
        # Method 2: H1 tags
        if not title:
            h1_tags = soup.find_all('h1')
            for h1 in h1_tags:
                h1_text = h1.get_text(strip=True)
                if h1_text and len(h1_text) > 5:
                    title = h1_text
                    logger.info(f"Found H1 title: {repr(title)}")
                    break
        
        # Method 3: Product name selectors
        if not title:
            selectors = ['.product-name', '.product-title', '.entry-title', '[data-testid="product-title"]']
            for selector in selectors:
                element = soup.select_one(selector)
                if element:
                    title = element.get_text(strip=True)
                    logger.info(f"Found title with selector {selector}: {repr(title)}")
                    break
        
        if title:
            # Clean up title
            for suffix in [' - Best4Systems', ' | Best4Systems', ' - PMC Telecom', ' - Headset Store']:
                title = re.sub(re.escape(suffix) + r'.*$', '', title, flags=re.IGNORECASE)
            product['title'] = title.strip()
            logger.info(f"Final title: {repr(product['title'])}")
        
        # PART NUMBER EXTRACTION - Look for specific patterns
        logger.info("=== LOOKING FOR PART NUMBERS ===")
        
        # Look for "part number: XXXXX" pattern specifically
        part_patterns = [
            r'part number[:\s]+([A-Z0-9\-]+)',
            r'product code[:\s]+([A-Z0-9\-]+)',
            r'model[:\s]+([A-Z0-9\-]+)',
            r'MPN[:\s]+([A-Z0-9\-]+)',
            r'SKU[:\s]+([A-Z0-9\-]+)',
        ]
        
        for pattern in part_patterns:
            matches = re.findall(pattern, page_text, re.IGNORECASE)
            if matches:
                logger.info(f"Pattern '{pattern}' found: {matches}")
                for match in matches:
                    if 3 <= len(match) <= 20:  # Reasonable length
                        product['part_number'] = match
                        logger.info(f"Using part number: {match}")
                        break
                if 'part_number' in product:
                    break
        
        # If no part number found, look for likely candidates
        if 'part_number' not in product:
            potential_parts = re.findall(r'\b[A-Z]{2,}[0-9\-]{2,}\b', page_text)
            if potential_parts:
                logger.info(f"Potential part numbers: {potential_parts[:5]}")
                product['part_number'] = potential_parts[0]
        
        # BRAND EXTRACTION
        logger.info("=== LOOKING FOR BRANDS ===")
        
        # First check title for known brands
        if 'title' in product:
            title_lower = product['title'].lower()
            brands = ['plantronics', 'poly', 'epos', 'sennheiser', 'jabra', 'logitech', 'project telecom', 'cisco', 'yealink']
            for brand in brands:
                if brand in title_lower:
                    product['brand'] = brand.title()
                    logger.info(f"Found brand in title: {brand}")
                    break
        
        # Check page text for brand patterns
        if 'brand' not in product:
            brand_lines = []
            lines = page_text.split('\n')
            for line in lines:
                if any(word in line.lower() for word in ['brand', 'manufacturer', 'made by']):
                    brand_lines.append(line.strip())
            
            if brand_lines:
                logger.info(f"Brand-related lines: {brand_lines[:3]}")
        
        # PRICE EXTRACTION (already working, but let's improve it)
        logger.info("=== LOOKING FOR PRICES ===")
        price_patterns = [
            r'£\s*([\d,]+\.?\d*)',
            r'\$\s*([\d,]+\.?\d*)',
            r'€\s*([\d,]+\.?\d*)',
            r'GBP\s*([\d,]+\.?\d*)',
            r'USD\s*([\d,]+\.?\d*)',
        ]
        
        for pattern in price_patterns:
            matches = re.findall(pattern, page_text)
            if matches:
                logger.info(f"Price pattern '{pattern}' found: {matches}")
                for match in matches:
                    try:
                        price_float = float(match.replace(',', ''))
                        if 1 <= price_float <= 10000:  # Reasonable range
                            currency = '£' if '£' in pattern else ('$' if '$' in pattern else '€')
                            product['price'] = f"{currency}{match}"
                            logger.info(f"Using price: {product['price']}")
                            break
                    except:
                        continue
                if 'price' in product:
                    break
        
        # DESCRIPTION EXTRACTION
        logger.info("=== LOOKING FOR DESCRIPTIONS ===")
        
        # Look for description in meta tags
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            desc = meta_desc.get('content').strip()
            if len(desc) > 20:
                product['description'] = desc
                logger.info(f"Found meta description: {desc[:100]}")
        
        # Look for product descriptions in common containers
        if 'description' not in product:
            desc_selectors = [
                '.product-description', '.description', '.product-details', 
                '.product-info', '.entry-content', '[data-testid="description"]'
            ]
            
            for selector in desc_selectors:
                elements = soup.select(selector)
                for element in elements:
                    desc = element.get_text(strip=True)
                    if 50 < len(desc) < 1000:
                        product['description'] = desc[:500]  # Limit length
                        logger.info(f"Found description with {selector}: {desc[:100]}")
                        break
                if 'description' in product:
                    break
        
        # Look for paragraph descriptions
        if 'description' not in product:
            paragraphs = soup.find_all('p')
            for para in paragraphs:
                desc = para.get_text(strip=True)
                if (100 < len(desc) < 800 and 
                    not any(word in desc.lower() for word in ['cookie', 'privacy', 'delivery', 'return'])):
                    product['description'] = desc
                    logger.info(f"Found paragraph description: {desc[:100]}")
                    break
        
        # Set defaults if nothing found
        if 'title' not in product:
            # Extract from URL as fallback
            url_parts = url.split('/')
            for part in reversed(url_parts):
                if part and len(part) > 5 and '-' in part:
                    title = part.replace('-', ' ').replace('.html', '').title()
                    product['title'] = title
                    logger.info(f"Generated title from URL: {title}")
                    break
            
            if 'title' not in product:
                product['title'] = f"Product from {url.split('//')[-1].split('/')[0]}"
        
        if 'description' not in product:
            product['description'] = f"Professional {product.get('title', 'product')} with advanced features."
        
        product['availability'] = 'Available'
        
        # FINAL DEBUG OUTPUT
        logger.info(f"=== FINAL EXTRACTION RESULTS FOR {url} ===")
        for key, value in product.items():
            if key != 'source_url':
                display_value = str(value)[:150] + ('...' if len(str(value)) > 150 else '')
                logger.info(f"{key.title()}: {display_value}")
        logger.info("=== END EXTRACTION RESULTS ===")
        
        return product

def scrape_urls_background(job_id, urls):
    """Background function to scrape URLs"""
    with app.app_context():
        job = ScrapingJob.query.get(job_id)
        scraper = UniversalProductScraper(delay=3)
        
        try:
            job.status = 'running'
            db.session.commit()
            
            for i, url in enumerate(urls):
                job.current_url = url
                job.completed_urls = i
                db.session.commit()
                
                # Scrape the product
                product_data = scraper.scrape_product(url)
                
                if product_data:
                    # Save to database
                    product = Product(
                        job_id=job_id,
                        title=product_data.get('title'),
                        price=product_data.get('price'),
                        description=product_data.get('description'),
                        part_number=product_data.get('part_number'),
                        ean=product_data.get('ean'),
                        brand=product_data.get('brand'),
                        color=product_data.get('color'),
                        condition=product_data.get('condition'),
                        image_url=product_data.get('image_url'),
                        additional_images=product_data.get('additional_images'),
                        source_url=product_data.get('source_url'),
                        features=product_data.get('features'),
                        availability=product_data.get('availability')
                    )
                    db.session.add(product)
                    db.session.commit()
                    logger.info(f"Saved product: {product_data.get('title', 'Unknown')}")
                else:
                    job.failed_urls += 1
                    logger.warning(f"Failed to scrape: {url}")
            
            # Mark job as completed
            job.status = 'completed'
            job.completed_at = datetime.utcnow()
            job.completed_urls = len(urls)
            db.session.commit()
            
            logger.info(f"Scraping job {job_id} completed successfully")
            
        except Exception as e:
            job.status = 'failed'
            job.error_message = str(e)
            db.session.commit()
            logger.error(f"Scraping job {job_id} failed: {str(e)}")

# API Routes
@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')

@app.route('/api/scrape', methods=['POST'])
def start_scraping():
    """Start a new scraping job"""
    try:
        data = request.get_json()
        
        if not data or 'urls' not in data:
            return jsonify({'error': 'No URLs provided'}), 400
        
        urls = [url.strip() for url in data['urls'] if url.strip()]
        
        if not urls:
            return jsonify({'error': 'No valid URLs provided'}), 400
        
        # Create new job
        job_id = str(uuid.uuid4())
        job = ScrapingJob(
            id=job_id,
            total_urls=len(urls),
            status='pending'
        )
        db.session.add(job)
        db.session.commit()
        
        # Start background scraping
        thread = threading.Thread(target=scrape_urls_background, args=(job_id, urls))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'job_id': job_id,
            'status': 'started',
            'total_urls': len(urls)
        })
        
    except Exception as e:
        logger.error(f"Error starting scraping job: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/job/<job_id>/status')
def get_job_status(job_id):
    """Get the status of a scraping job"""
    try:
        job = ScrapingJob.query.get(job_id)
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        return jsonify({
            'id': job.id,
            'status': job.status,
            'total_urls': job.total_urls,
            'completed_urls': job.completed_urls,
            'failed_urls': job.failed_urls,
            'current_url': job.current_url,
            'progress': (job.completed_urls / job.total_urls * 100) if job.total_urls > 0 else 0,
            'error_message': job.error_message
        })
        
    except Exception as e:
        logger.error(f"Error getting job status: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/job/<job_id>/products')
def get_job_products(job_id):
    """Get all products from a scraping job"""
    try:
        job = ScrapingJob.query.get(job_id)
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        products = Product.query.filter_by(job_id=job_id).all()
        
        product_data = []
        for product in products:
            product_data.append({
                'id': product.id,
                'title': product.title,
                'price': product.price,
                'description': product.description,
                'part_number': product.part_number,
                'ean': product.ean,
                'brand': product.brand,
                'color': product.color,
                'condition': product.condition,
                'image_url': product.image_url,
                'additional_images': product.additional_images,
                'source_url': product.source_url,
                'features': product.features,
                'availability': product.availability
            })
        
        return jsonify({'products': product_data})
        
    except Exception as e:
        logger.error(f"Error getting job products: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/job/<job_id>/export/shopify')
def export_shopify_csv(job_id):
    """Export products as Shopify CSV"""
    try:
        job = ScrapingJob.query.get(job_id)
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        products = Product.query.filter_by(job_id=job_id).all()
        
        if not products:
            return jsonify({'error': 'No products found'}), 404
        
        # Create CSV in memory
        output = io.StringIO()
        
        # Shopify CSV headers
        fieldnames = [
            'Handle', 'Title', 'Body (HTML)', 'Vendor', 'Product Category', 'Type',
            'Tags', 'Published', 'Option1 Name', 'Option1 Value', 'Option2 Name', 'Option2 Value',
            'Option3 Name', 'Option3 Value', 'Variant SKU', 'Variant Grams', 'Variant Inventory Tracker',
            'Variant Inventory Qty', 'Variant Inventory Policy', 'Variant Fulfillment Service',
            'Variant Price', 'Variant Compare At Price', 'Variant Requires Shipping', 'Variant Taxable',
            'Variant Barcode', 'Image Src', 'Image Position', 'Image Alt Text', 'Gift Card',
            'SEO Title', 'SEO Description', 'Cost per item', 'Status'
        ]
        
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        for product in products:
            # Generate handle from title
            handle = ''
            if product.title:
                handle = re.sub(r'[^a-zA-Z0-9\s-]', '', product.title.lower())
                handle = re.sub(r'\s+', '-', handle).strip('-')
            
            # Clean price
            price = ''
            if product.price:
                price_match = re.search(r'([\d,]+\.?\d*)', product.price)
                if price_match:
                    price = price_match.group(1).replace(',', '')
            
            row = {
                'Handle': handle,
                'Title': product.title or '',
                'Body (HTML)': product.description or '',
                'Vendor': product.brand or '',
                'Published': 'TRUE',
                'Variant SKU': product.part_number or '',
                'Variant Inventory Tracker': 'shopify',
                'Variant Inventory Qty': '10',  # Default quantity
                'Variant Inventory Policy': 'deny',
                'Variant Fulfillment Service': 'manual',
                'Variant Price': price,
                'Variant Requires Shipping': 'TRUE',
                'Variant Taxable': 'TRUE',
                'Variant Barcode': product.ean or '',
                'Image Src': product.image_url or '',
                'Image Position': '1',
                'Image Alt Text': product.title or '',
                'Gift Card': 'FALSE',
                'SEO Title': product.title or '',
                'SEO Description': product.description[:160] if product.description else '',
                'Status': 'active'
            }
            
            writer.writerow(row)
        
        # Create file response
        output.seek(0)
        file_data = io.BytesIO(output.getvalue().encode('utf-8'))
        
        filename = f'shopify_products_{job_id[:8]}_{datetime.now().strftime("%Y%m%d")}.csv'
        
        return send_file(
            file_data,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        logger.error(f"Error exporting CSV: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/jobs')
def list_jobs():
    """List all scraping jobs"""
    try:
        jobs = ScrapingJob.query.order_by(ScrapingJob.created_at.desc()).limit(20).all()
        
        job_data = []
        for job in jobs:
            job_data.append({
                'id': job.id,
                'status': job.status,
                'total_urls': job.total_urls,
                'completed_urls': job.completed_urls,
                'failed_urls': job.failed_urls,
                'created_at': job.created_at.isoformat(),
                'completed_at': job.completed_at.isoformat() if job.completed_at else None
            })
        
        return jsonify({'jobs': job_data})
        
    except Exception as e:
        logger.error(f"Error listing jobs: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

# Health check endpoint
@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})

if __name__ == '__main__':
    # Get port from environment variable for deployment
    port = int(os.environ.get('PORT', 5000))
    
    # Create database tables
    with app.app_context():
        db.create_all()
        logger.info("Database tables created successfully")
    
    # Run the app
    logger.info(f"Starting app on port {port}")
    app.run(debug=False, host='0.0.0.0', port=port)
