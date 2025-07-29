# app.py - Complete Flask Application with Aggressive Best4Systems Scraping
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
    status = db.Column(db.String(20), default='pending')  # pending, running, completed, failed
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

class ProductScraper:
    def __init__(self, delay=2):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
    
    def scrape_product(self, url):
        """Scrape a single product from best4systems.co.uk"""
        try:
            logger.info(f"Scraping: {url}")
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            product_data = self.extract_product_data(soup, url)
            
            time.sleep(self.delay)  # Be respectful to the server
            return product_data
            
        except Exception as e:
            logger.error(f"Error scraping {url}: {str(e)}")
            return None
    
    def extract_product_data(self, soup, url):
        """Super aggressive extraction specifically for Best4Systems"""
        product = {'source_url': url}
        
        # Get all text from the page
        page_text = soup.get_text()
        
        # Extract title from page title tag
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text(strip=True)
            # Clean up title
            title = re.sub(r'\s*-\s*Best4Systems.*$', '', title, flags=re.IGNORECASE)
            title = re.sub(r'\s*\|\s*Best4Systems.*$', '', title, flags=re.IGNORECASE)
            if title and len(title) > 5:
                product['title'] = title
        
        # Look for specific patterns in the page text
        # Best4Systems uses pipe-separated tables like: "Manufacturer Part # | 1001138"
        
        # Find part number
        part_patterns = [
            r'Manufacturer Part #\s*\|\s*([^\|\n]+)',
            r'Part Number\s*\|\s*([^\|\n]+)', 
            r'Model\s*\|\s*([^\|\n]+)',
            r'Part #\s*:?\s*([A-Z0-9]+)',
            r'SKU\s*:?\s*([A-Z0-9]+)'
        ]
        
        for pattern in part_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                part_num = match.group(1).strip()
                if part_num and any(char.isdigit() for char in part_num):
                    product['part_number'] = part_num
                    break
        
        # Find EAN
        ean_patterns = [
            r'EAN\s*\|\s*([^\|\n]+)',
            r'EAN\s*:?\s*(\d{12,14})',
            r'Barcode\s*:?\s*(\d{12,14})'
        ]
        
        for pattern in ean_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                ean = match.group(1).strip()
                if ean.isdigit() and len(ean) >= 12:
                    product['ean'] = ean
                    break
        
        # Find colour
        colour_patterns = [
            r'Colour\s*\|\s*([^\|\n]+)',
            r'Color\s*\|\s*([^\|\n]+)',
            r'Colour\s*:?\s*([A-Za-z\s]+)'
        ]
        
        for pattern in colour_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                colour = match.group(1).strip()
                if colour and len(colour) < 50:
                    product['color'] = colour
                    break
        
        # Find condition
        condition_patterns = [
            r'Condition\s*\|\s*([^\|\n]+)',
            r'Condition\s*:?\s*([A-Za-z\s]+)'
        ]
        
        for pattern in condition_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                condition = match.group(1).strip()
                if condition and len(condition) < 20:
                    product['condition'] = condition
                    break
        
        # Find brand from title
        if 'title' in product:
            title_lower = product['title'].lower()
            brands = ['epos', 'sennheiser', 'jabra', 'plantronics', 'logitech', 'poly', 'cisco', 'yealink']
            for brand in brands:
                if brand in title_lower:
                    product['brand'] = brand.upper()
                    break
        
        # Find price (Best4Systems might load prices via JS, so this might not work)
        price_patterns = [
            r'£\s*([\d,]+\.?\d*)',
            r'Price\s*:?\s*£\s*([\d,]+\.?\d*)',
            r'Cost\s*:?\s*£\s*([\d,]+\.?\d*)',
            r'\b([\d,]+\.?\d+)\s*GBP\b'
        ]
        
        for pattern in price_patterns:
            match = re.search(pattern, page_text)
            if match:
                price = match.group(1).replace(',', '')
                try:
                    # Validate it's a reasonable price (between £1 and £10000)
                    price_float = float(price)
                    if 1 <= price_float <= 10000:
                        product['price'] = f"£{price}"
                        break
                except:
                    continue
        
        # Look for description in various places
        desc_patterns = [
            r'product[_-]?description[^>]*>([^<]+)',
            r'description[^>]*>([^<]+)',
        ]
        
        html_content = str(soup)
        for pattern in desc_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                desc = match.group(1).strip()
                if len(desc) > 20:
                    product['description'] = desc[:500]
                    break
        
        # If no description found, use title as description
        if 'description' not in product and 'title' in product:
            product['description'] = f"Professional {product['title']} - High quality communication device."
        
        # Set default availability
        product['availability'] = 'Available'
        
        # Look for images
        img_tags = soup.find_all('img')
        images = []
        for img in img_tags:
            src = img.get('src', '')
            if src and 'product' in src.lower():
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = urljoin(url, src)
                if src not in images:
                    images.append(src)
        
        if images:
            product['image_url'] = images[0]
        
        # Debug logging - this will show in Render logs
        logger.info(f"=== EXTRACTION RESULTS FOR {url} ===")
        logger.info(f"Title: {product.get('title', 'NOT FOUND')}")
        logger.info(f"Part Number: {product.get('part_number', 'NOT FOUND')}")
        logger.info(f"EAN: {product.get('ean', 'NOT FOUND')}")
        logger.info(f"Brand: {product.get('brand', 'NOT FOUND')}")
        logger.info(f"Color: {product.get('color', 'NOT FOUND')}")
        logger.info(f"Condition: {product.get('condition', 'NOT FOUND')}")
        logger.info(f"Price: {product.get('price', 'NOT FOUND')}")
        logger.info(f"Description: {product.get('description', 'NOT FOUND')[:100]}...")
        logger.info("=== END EXTRACTION RESULTS ===")
        
        # Check if we found ANY useful data
        useful_fields = ['title', 'part_number', 'ean', 'brand', 'color', 'condition']
        found_fields = [field for field in useful_fields if field in product and product[field]]
        
        logger.info(f"Found {len(found_fields)} useful fields: {found_fields}")
        
        return product

def scrape_urls_background(job_id, urls):
    """Background function to scrape URLs"""
    with app.app_context():
        job = ScrapingJob.query.get(job_id)
        scraper = ProductScraper(delay=2)
        
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
