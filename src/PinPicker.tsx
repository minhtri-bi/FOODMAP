import { useEffect, useId, useRef, useState } from 'react';
import * as L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './discovery.css';

interface Props {
  latitude: number | null;
  longitude: number | null;
  onChange: (lat: number, lon: number) => void;
}

const defaultCenter: L.LatLngTuple = [10.7769, 106.7009];

function coordinatePair(latitude: number | null, longitude: number | null): L.LatLngTuple | null {
  return latitude !== null && longitude !== null && Number.isFinite(latitude) && Number.isFinite(longitude)
    && latitude >= -90 && latitude <= 90 && longitude >= -180 && longitude <= 180
    ? [latitude, longitude] : null;
}

export function PinPicker({ latitude, longitude, onChange }: Props) {
  const id = useId();
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const marker = useRef<L.CircleMarker | null>(null);
  const change = useRef(onChange);
  const coordinates = useRef({ latitude, longitude });
  const [loadRequest, setLoadRequest] = useState(0);
  const [mapError, setMapError] = useState('');
  const [tileState, setTileState] = useState<'loading' | 'ready' | 'error'>('loading');
  const pair = coordinatePair(latitude, longitude);
  const hasPartialOrInvalidPin = !pair && (latitude !== null || longitude !== null);

  useEffect(() => {
    change.current = onChange;
  }, [onChange]);

  useEffect(() => {
    coordinates.current = { latitude, longitude };
  }, [latitude, longitude]);

  useEffect(() => {
    if (loadRequest === 0 || !container.current) return;
    let instance: L.Map | null = null;
    let tiles: L.TileLayer | null = null;
    let resize: ResizeObserver | null = null;
    let active = true;
    let tileFailed = false;
    try {
      const initial = coordinatePair(coordinates.current.latitude, coordinates.current.longitude);
      instance = L.map(container.current, {
        center: initial ?? defaultCenter,
        zoom: initial ? 16 : 13,
        attributionControl: false,
        worldCopyJump: true,
        minZoom: 1,
        maxZoom: 19,
      });
      map.current = instance;
      const currentMap = instance;
      currentMap.on('click', (event: L.LeafletMouseEvent) => {
        const point = event.latlng.wrap();
        if (coordinatePair(point.lat, point.lng)) change.current(point.lat, point.lng);
      });
      tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        minZoom: 1,
        maxZoom: 19,
        keepBuffer: 0,
        updateWhenIdle: true,
        updateWhenZooming: false,
      });
      tiles.on('loading', () => {
        if (!active) return;
        tileFailed = false;
        setTileState('loading');
      });
      tiles.on('tileerror', () => {
        if (!active) return;
        tileFailed = true;
        setTileState('error');
      });
      tiles.on('load', () => {
        if (active && !tileFailed) setTileState('ready');
      });
      tiles.addTo(currentMap);
      resize = new ResizeObserver(() => {
        if (active) currentMap.invalidateSize({ pan: false });
      });
      resize.observe(container.current);
    } catch {
      setMapError('The map could not be initialized. Use the decimal coordinate inputs, or reload the map.');
      resize?.disconnect();
      tiles?.off();
      instance?.remove();
      map.current = null;
      marker.current = null;
    }
    return () => {
      active = false;
      resize?.disconnect();
      tiles?.off();
      if (map.current === instance) {
        instance?.off();
        instance?.remove();
        map.current = null;
        marker.current = null;
      }
    };
  }, [loadRequest]);

  useEffect(() => {
    const currentMap = map.current;
    if (!currentMap) return;
    const selected = coordinatePair(latitude, longitude);
    if (!selected) {
      marker.current?.remove();
      marker.current = null;
      return;
    }
    if (marker.current) {
      marker.current.setLatLng(selected);
    } else {
      marker.current = L.circleMarker(selected, {
        radius: 9,
        color: '#ffffff',
        weight: 3,
        fillColor: '#155e83',
        fillOpacity: 1,
        interactive: false,
      }).addTo(currentMap);
    }
    const center = currentMap.getCenter();
    if (center.lat !== selected[0] || center.lng !== selected[1]) {
      currentMap.setView(selected, Math.max(currentMap.getZoom(), 15), { animate: false });
    }
  }, [latitude, longitude, loadRequest]);

  return <section className="pin-picker" aria-labelledby={`${id}-heading`}>
    <h3 id={`${id}-heading`}>Manual branch pin</h3>
    <p id={`${id}-instructions`} className="hint">Optionally load the map and click the exact branch to update its coordinates. Use the decimal latitude and longitude inputs in the form as the keyboard alternative. A pin is a draft, not a confirmed branch.</p>
    <p className="hint">Loading requests visible map tiles from OpenStreetMap, which receives your IP address and the viewed map area. Panning and zooming request more visible tiles. No GPS, address lookup or route calculation is used.</p>
    <button type="button" aria-controls={`${id}-map`} onClick={() => {
      setMapError('');
      setTileState('loading');
      setLoadRequest(previous => previous + 1);
    }}>{loadRequest === 0 ? 'Load map' : 'Reload map'}</button>
    {loadRequest === 0 && <p className="hint">Map not loaded. No external tiles have been requested. The default view is central Ho Chi Minh City, not your location or a confirmed pin.</p>}
    <div className="pin-picker-frame" hidden={loadRequest === 0}>
      <div id={`${id}-map`} ref={container} className="pin-picker-map" role="region" aria-label="Manual branch pin map" aria-describedby={`${id}-instructions ${id}-selection`} />
      <p className="pin-picker-attribution">Map data © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a> · <a href="https://opendatacommons.org/licenses/odbl/1-0/" target="_blank" rel="noopener noreferrer">ODbL</a></p>
    </div>
    <p id={`${id}-selection`} role="status" className="hint">{pair
      ? `Draft pin: ${pair[0].toFixed(6)}, ${pair[1].toFixed(6)}. Verify the branch before confirming and saving.`
      : hasPartialOrInvalidPin
        ? 'No valid pin: enter both finite coordinates within latitude −90 to 90 and longitude −180 to 180, or choose a point on the map.'
        : 'No pin selected. The central Ho Chi Minh City view is only a starting point.'}</p>
    {mapError ? <p role="alert" className="error">{mapError}</p> : loadRequest > 0 && <p role={tileState === 'error' ? 'alert' : 'status'} className={tileState === 'error' ? 'error' : 'hint'}>{tileState === 'error'
      ? 'Some map tiles could not load. The map may be incomplete; use decimal inputs or reload when connected. Your draft coordinates are unchanged.'
      : tileState === 'loading' ? 'Loading visible map tiles… Decimal coordinate inputs remain available.'
        : 'Map tiles loaded. Click a branch location to set the draft pin.'}</p>}
  </section>;
}
