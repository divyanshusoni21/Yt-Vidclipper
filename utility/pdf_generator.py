import os
import tempfile
from datetime import datetime, timedelta
from django.template.loader import render_to_string
from django.conf import settings
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration
import os
import tempfile
from datetime import datetime, timedelta
from django.template.loader import render_to_string
from django.conf import settings
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration

from io import BytesIO
import logging

logger = logging.getLogger(__name__)

class PDFGenerator:
    """Utility class for generating PDFs from HTML templates"""
    
    @staticmethod
    def generate_pdf(customeQuery:dict):
        """
        Generate PDF for a given PDF data
        
        Args:
            customeQuery: Customer query data
            generated_by: User who is generating the PDF
            
        Returns:
            tuple: (pdf_content, filename)
        """
        try:
            
            
            # Render HTML template
            html_content = render_to_string('quote_template.html', customeQuery)
            
            # Generate PDF filename
            filename = f"{customeQuery['customer_name']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            
            # Convert HTML to PDF
            pdf_content = PDFGenerator._html_to_pdf(html_content)
            
            return pdf_content, filename
            
        except Exception as e:
            logger.error(f"Error generating PDF for customer : {customeQuery['customer_name']}: {str(e)}")
            raise
    
    @staticmethod
    def _html_to_pdf(html_content):
        """
        Convert HTML content to PDF using WeasyPrint
        
        Args:
            html_content: HTML string content
            
        Returns:
            bytes: PDF content
        """
        try:
            # Configure fonts
            font_config = FontConfiguration()
            
            # Create HTML object
            html = HTML(string=html_content)
            
            # Generate PDF
            pdf = html.write_pdf(
                font_config=font_config,
                optimize_images=True,
                jpeg_quality=85
            )
            
            return pdf
            
        except Exception as e:
            logger.error(f"Error converting HTML to PDF: {str(e)}")
            raise
    
    @staticmethod
    def save_pdf_to_temp(pdf_content, filename):
        """
        Save PDF content to a temporary file
        
        Args:
            pdf_content: PDF bytes content
            filename: Name for the file
            
        Returns:
            str: Path to temporary file
        """
        try:
            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix='.pdf',
                prefix='customer_query_'
            )
            
            # Write PDF content
            temp_file.write(pdf_content)
            temp_file.close()
            
            return temp_file.name
            
        except Exception as e:
            logger.error(f"Error saving PDF to temp file: {str(e)}")
            raise
    
    @staticmethod
    def cleanup_temp_file(file_path):
        """
        Clean up temporary file
        
        Args:
            file_path: Path to temporary file
        """
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
        except Exception as e:
            logger.warning(f"Error cleaning up temp file {file_path}: {str(e)}")
    
   