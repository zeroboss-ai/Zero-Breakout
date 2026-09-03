/**
 * ZeroBreakout Minimalist Canvas Candlestick & Moving Average Chart
 * High-performance, Retina-ready, Zerodha-style with crosshairs and tooltips.
 */

class BreakoutChart {
  constructor(canvasElement) {
    this.canvas = canvasElement;
    this.ctx = canvasElement.getContext('2d');
    this.data = [];
    this.pivotPrice = null;
    this.hoverIndex = null;
    
    this.margin = { top: 16, right: 65, bottom: 28, left: 10 };
    this.volumeHeightPct = 0.20; // 20% for volume at bottom

    this._bindEvents();
  }

  setData(candles, pivotPrice = null) {
    this.data = candles || [];
    this.pivotPrice = pivotPrice;
    this.hoverIndex = null;
    this.render();
  }

  _bindEvents() {
    const handleMove = (clientX, clientY) => {
      if (!this.data.length) return;
      const rect = this.canvas.getBoundingClientRect();
      const x = clientX - rect.left;
      
      const plotWidth = rect.width - this.margin.left - this.margin.right;
      if (x < this.margin.left || x > rect.width - this.margin.right) {
        this.hoverIndex = null;
      } else {
        const step = plotWidth / this.data.length;
        const idx = Math.floor((x - this.margin.left) / step);
        this.hoverIndex = Math.max(0, Math.min(this.data.length - 1, idx));
      }
      this.render();
    };

    this.canvas.addEventListener('mousemove', (e) => handleMove(e.clientX, e.clientY));
    this.canvas.addEventListener('mouseleave', () => {
      this.hoverIndex = null;
      this.render();
    });

    this.canvas.addEventListener('touchmove', (e) => {
      if (e.touches.length > 0) {
        handleMove(e.touches[0].clientX, e.touches[0].clientY);
      }
    }, { passive: true });

    this.canvas.addEventListener('touchend', () => {
      this.hoverIndex = null;
      this.render();
    });

    window.addEventListener('resize', () => this.render());
  }

  render() {
    if (!this.canvas || !this.ctx) return;

    // Retina display scaling
    const dpr = window.devicePixelRatio || 1;
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const width = rect.width || 400;
    const height = 280;

    this.canvas.width = width * dpr;
    this.canvas.height = height * dpr;
    this.canvas.style.width = `${width}px`;
    this.canvas.style.height = `${height}px`;

    const ctx = this.ctx;
    ctx.resetTransform();
    ctx.scale(dpr, dpr);

    ctx.clearRect(0, 0, width, height);

    if (!this.data || this.data.length === 0) {
      ctx.fillStyle = '#94A3B8';
      ctx.font = '13px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('No historical data available', width / 2, height / 2);
      return;
    }

    const plotWidth = width - this.margin.left - this.margin.right;
    const totalPlotHeight = height - this.margin.top - this.margin.bottom;
    const pricePlotHeight = totalPlotHeight * (1 - this.volumeHeightPct);
    const volumePlotHeight = totalPlotHeight * this.volumeHeightPct;
    const volumeTopY = this.margin.top + pricePlotHeight;

    // Determine min/max price
    let minPrice = Infinity;
    let maxPrice = -Infinity;
    let maxVolume = 0;

    this.data.forEach(d => {
      if (d.low < minPrice) minPrice = d.low;
      if (d.high > maxPrice) maxPrice = d.high;
      if (d.sma_20 && d.sma_20 < minPrice) minPrice = d.sma_20;
      if (d.sma_20 && d.sma_20 > maxPrice) maxPrice = d.sma_20;
      if (d.sma_50 && d.sma_50 < minPrice) minPrice = d.sma_50;
      if (d.sma_50 && d.sma_50 > maxPrice) maxPrice = d.sma_50;
      if (d.volume > maxVolume) maxVolume = d.volume;
    });

    if (this.pivotPrice) {
      if (this.pivotPrice < minPrice) minPrice = this.pivotPrice;
      if (this.pivotPrice > maxPrice) maxPrice = this.pivotPrice;
    }

    // Add 4% padding on price axis
    const priceRange = maxPrice - minPrice || 1;
    const paddedMin = minPrice - priceRange * 0.04;
    const paddedMax = maxPrice + priceRange * 0.04;
    const paddedRange = paddedMax - paddedMin;

    const priceToY = (p) => this.margin.top + pricePlotHeight * (1 - (p - paddedMin) / paddedRange);
    const volToY = (v) => volumeTopY + volumePlotHeight * (1 - (maxVolume ? v / maxVolume : 0));

    // Draw Subtle Grid & Y-Axis Labels
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const gridColor = isDark ? '#232832' : '#F0F3F6';
    const textColor = isDark ? '#64748B' : '#94A3B8';
    const greenColor = isDark ? '#10B981' : '#00B386';
    const redColor = isDark ? '#F43F5E' : '#EB5B3C';

    ctx.strokeStyle = gridColor;
    ctx.lineWidth = 1;
    ctx.font = '10px tabular-nums, sans-serif';
    ctx.fillStyle = textColor;
    ctx.textAlign = 'left';

    const ySteps = 4;
    for (let i = 0; i <= ySteps; i++) {
      const p = paddedMin + (paddedRange / ySteps) * i;
      const y = priceToY(p);
      ctx.beginPath();
      ctx.moveTo(this.margin.left, y);
      ctx.lineTo(width - this.margin.right, y);
      ctx.stroke();

      ctx.fillText(`₹${p.toFixed(1)}`, width - this.margin.right + 6, y + 3);
    }

    // Candle Step Calculation
    const n = this.data.length;
    const candleWidth = Math.max(2, (plotWidth / n) * 0.7);
    const step = plotWidth / n;

    // Draw Volume Bars
    this.data.forEach((d, i) => {
      const cx = this.margin.left + i * step + step / 2;
      const vy = volToY(d.volume);
      const isUp = d.close >= d.open;

      ctx.fillStyle = isUp 
        ? (isDark ? 'rgba(16, 185, 129, 0.25)' : 'rgba(0, 179, 134, 0.25)')
        : (isDark ? 'rgba(244, 63, 94, 0.25)' : 'rgba(235, 91, 60, 0.25)');

      ctx.fillRect(cx - candleWidth / 2, vy, candleWidth, height - this.margin.bottom - vy);
    });

    // Draw Candlesticks
    this.data.forEach((d, i) => {
      const cx = this.margin.left + i * step + step / 2;
      const openY = priceToY(d.open);
      const closeY = priceToY(d.close);
      const highY = priceToY(d.high);
      const lowY = priceToY(d.low);

      const isUp = d.close >= d.open;
      const candleColor = isUp ? greenColor : redColor;

      // Wick
      ctx.strokeStyle = candleColor;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(cx, highY);
      ctx.lineTo(cx, lowY);
      ctx.stroke();

      // Body
      const topY = Math.min(openY, closeY);
      const bodyHeight = Math.max(1.5, Math.abs(closeY - openY));
      ctx.fillStyle = candleColor;
      ctx.fillRect(cx - candleWidth / 2, topY, candleWidth, bodyHeight);
    });

    // Draw 20 SMA Line (Blue)
    this._drawLineSeries(ctx, this.data, 'sma_20', '#387ED1', 1.8, step, priceToY);

    // Draw 50 SMA Line (Amber)
    this._drawLineSeries(ctx, this.data, 'sma_50', '#F59E0B', 1.6, step, priceToY);

    // Draw Breakout Pivot Horizontal Line if available
    if (this.pivotPrice) {
      const py = priceToY(this.pivotPrice);
      ctx.save();
      ctx.strokeStyle = '#10B981';
      ctx.lineWidth = 1.4;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(this.margin.left, py);
      ctx.lineTo(width - this.margin.right, py);
      ctx.stroke();

      // Pivot label tag
      ctx.fillStyle = '#10B981';
      ctx.fillRect(width - this.margin.right, py - 9, 58, 18);
      ctx.fillStyle = '#FFFFFF';
      ctx.font = 'bold 9px sans-serif';
      ctx.fillText(`PIVOT ₹${this.pivotPrice.toFixed(0)}`, width - this.margin.right + 3, py + 3);
      ctx.restore();
    }

    // X-Axis Dates (Show 4-5 labels)
    ctx.fillStyle = textColor;
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    const dateInterval = Math.max(1, Math.floor(n / 4));
    for (let i = 0; i < n; i += dateInterval) {
      const d = this.data[i];
      const cx = this.margin.left + i * step + step / 2;
      const formattedDate = this._formatDate(d.date);
      ctx.fillText(formattedDate, cx, height - this.margin.bottom + 16);
    }

    // Crosshair & Tooltip on Hover
    if (this.hoverIndex !== null && this.data[this.hoverIndex]) {
      this._renderCrosshair(ctx, width, height, step, priceToY, isDark);
    }
  }

  _drawLineSeries(ctx, data, key, color, lineWidth, step, priceToY) {
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.beginPath();
    let started = false;

    data.forEach((d, i) => {
      const val = d[key];
      if (val !== null && val !== undefined) {
        const cx = this.margin.left + i * step + step / 2;
        const cy = priceToY(val);
        if (!started) {
          ctx.moveTo(cx, cy);
          started = true;
        } else {
          ctx.lineTo(cx, cy);
        }
      }
    });
    ctx.stroke();
    ctx.restore();
  }

  _renderCrosshair(ctx, width, height, step, priceToY, isDark) {
    const d = this.data[this.hoverIndex];
    const cx = this.margin.left + this.hoverIndex * step + step / 2;
    const cy = priceToY(d.close);

    // Crosshair lines
    ctx.save();
    ctx.strokeStyle = isDark ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.25)';
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);

    // Vertical line
    ctx.beginPath();
    ctx.moveTo(cx, this.margin.top);
    ctx.lineTo(cx, height - this.margin.bottom);
    ctx.stroke();

    // Horizontal line
    ctx.beginPath();
    ctx.moveTo(this.margin.left, cy);
    ctx.lineTo(width - this.margin.right, cy);
    ctx.stroke();
    ctx.restore();

    // Floating Tooltip Badge
    const tooltipText = `O: ${d.open}  H: ${d.high}  L: ${d.low}  C: ${d.close}  (${d.date})`;
    ctx.font = '11px -apple-system, sans-serif';
    ctx.fillStyle = isDark ? '#2D333F' : '#1E293B';
    const textWidth = ctx.measureText(tooltipText).width + 16;
    const tooltipX = Math.max(10, Math.min(width - textWidth - 10, cx - textWidth / 2));
    
    ctx.fillRect(tooltipX, this.margin.top - 12, textWidth, 20);
    ctx.fillStyle = '#FFFFFF';
    ctx.textAlign = 'left';
    ctx.fillText(tooltipText, tooltipX + 8, this.margin.top + 2);
  }

  _formatDate(dateStr) {
    if (!dateStr) return '';
    try {
      const parts = dateStr.split('-');
      if (parts.length === 3) {
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        return `${parts[2]} ${months[parseInt(parts[1], 10) - 1]}`;
      }
    } catch (e) {}
    return dateStr;
  }
}

window.BreakoutChart = BreakoutChart;
