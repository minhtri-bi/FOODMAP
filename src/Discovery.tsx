import { useId, useState } from 'react';
import type { FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { errorMessage } from './api';
import './discovery.css';

export interface PlaceChoice {
  osm_id: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
}

interface Props {
  onChoose: (choice: PlaceChoice) => boolean;
}

interface Search {
  q: string;
  latitude?: number;
  longitude?: number;
}

const discoverySchema = z.object({
  data: z.array(z.object({
    osm_id: z.string().min(1),
    name: z.string(),
    address: z.string(),
    latitude: z.number().finite().min(-90).max(90),
    longitude: z.number().finite().min(-180).max(180),
    category: z.string(),
    source_url: z.string(),
    observed_at: z.string(),
    license: z.string(),
    distance_km: z.number().finite().nonnegative().nullable(),
  })),
  meta: z.object({
    total: z.number().int().nonnegative(),
    coverage: z.string(),
    observed_at: z.string().nullable(),
  }),
});

async function findPlaces(search: Search, signal: AbortSignal) {
  const params = new URLSearchParams({ q: search.q, limit: '10' });
  if (search.latitude !== undefined && search.longitude !== undefined) {
    params.set('latitude', String(search.latitude));
    params.set('longitude', String(search.longitude));
  }
  let response: Response;
  try {
    response = await fetch(`/api/v1/discovery?${params}`, { signal });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new Error('Cannot reach the local discovery server. Check that it is running and search again.');
  }
  if (!response.ok) {
    throw new Error(`Discovery failed (HTTP ${response.status}). Search again; no place was saved.`);
  }
  const parsed = discoverySchema.safeParse(await response.json().catch(() => null));
  if (!parsed.success) throw new Error('Discovery returned an invalid response. No results were accepted.');
  return parsed.data;
}

function observationDate(value: string | null): string {
  if (!value) return 'Unknown';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Unknown' : date.toLocaleString();
}

function sourceLink(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && (url.hostname === 'openstreetmap.org' || url.hostname === 'www.openstreetmap.org')
      ? url.href : null;
  } catch {
    return null;
  }
}

export function Discovery({ onChoose }: Props) {
  const id = useId();
  const [query, setQuery] = useState('');
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  const [inputError, setInputError] = useState('');
  const [search, setSearch] = useState<Search | null>(null);
  const [chosen, setChosen] = useState('');
  const results = useQuery({
    queryKey: ['discovery', search],
    queryFn: ({ signal }) => {
      if (!search) throw new Error('Enter a name or address first.');
      return findPlaces(search, signal);
    },
    enabled: search !== null,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const q = query.trim();
    const latText = latitude.trim();
    const lonText = longitude.trim();
    if (!q) {
      setInputError('Enter a restaurant name or street address.');
      return;
    }
    if (Boolean(latText) !== Boolean(lonText)) {
      setInputError('Enter both manual origin coordinates, or leave both empty.');
      return;
    }
    if (!event.currentTarget.checkValidity()) {
      setInputError('Use finite decimal coordinates: latitude −90 to 90, longitude −180 to 180.');
      return;
    }
    const lat = Number(latText);
    const lon = Number(lonText);
    if (latText && (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180)) {
      setInputError('Use finite decimal coordinates: latitude −90 to 90, longitude −180 to 180.');
      return;
    }
    const next: Search = latText ? { q, latitude: lat, longitude: lon } : { q };
    setInputError('');
    setChosen('');
    if (search?.q === next.q && search.latitude === next.latitude && search.longitude === next.longitude) {
      void results.refetch();
    } else {
      setSearch(next);
    }
  }

  return <section className="discovery-panel" aria-labelledby={`${id}-heading`}>
    <h2 id={`${id}-heading`}>Discover regional places</h2>
    <p className="muted">Search a locally stored OpenStreetMap snapshot by name or address. Coverage is limited, not a complete restaurant directory; details may be outdated.</p>
    <p className="hint">Source: © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a>, under the <a href="https://opendatacommons.org/licenses/odbl/1-0/" target="_blank" rel="noopener noreferrer">Open Database License (ODbL)</a>. Search reads the local snapshot, not a live map directory.</p>
    <form onSubmit={submit} noValidate>
      <label htmlFor={`${id}-query`}>Name or address</label>
      <div className="discovery-search-row">
        <input id={`${id}-query`} type="search" value={query} onChange={event => setQuery(event.target.value)} required autoComplete="off" aria-describedby={`${id}-error`} aria-invalid={Boolean(inputError) || undefined} />
        <button type="submit" className="primary" disabled={results.isFetching}>{results.isFetching ? 'Searching…' : 'Search places'}</button>
      </div>
      <fieldset className="discovery-origin">
        <legend>Manual ranking origin <span className="optional">optional</span></legend>
        <div className="coordinate-fields">
          <label htmlFor={`${id}-latitude`}>Latitude<input id={`${id}-latitude`} type="number" inputMode="decimal" min={-90} max={90} step="any" value={latitude} onChange={event => setLatitude(event.target.value)} aria-describedby={`${id}-origin-note ${id}-error`} /></label>
          <label htmlFor={`${id}-longitude`}>Longitude<input id={`${id}-longitude`} type="number" inputMode="decimal" min={-180} max={180} step="any" value={longitude} onChange={event => setLongitude(event.target.value)} aria-describedby={`${id}-origin-note ${id}-error`} /></label>
        </div>
        <p id={`${id}-origin-note`} className="hint">Enter both or neither. This is not GPS. Origin changes ranking only; distant matches are not excluded. Distances are straight-line estimates, not travel routes.</p>
      </fieldset>
      <div id={`${id}-error`}>{inputError && <p className="error" role="alert">{inputError}</p>}</div>
    </form>
    <div role="status" className="discovery-status">
      {!search ? 'No search yet. Enter a name or address to query the local snapshot.' : results.isFetching ? 'Searching the local snapshot…' : results.isError ? '' : results.data ? `${results.data.data.length} result${results.data.data.length === 1 ? '' : 's'} shown for “${search.q}”.` : 'Search results are not available yet.'}
    </div>
    {results.isError && <p role="alert" className="error">{errorMessage(results.error)}</p>}
    {search && results.data && !results.isFetching && !results.isError && <>
      <div className="discovery-coverage">
        <p><strong>Snapshot coverage:</strong> {results.data.meta.coverage.trim() || 'Unknown; completeness is not established.'}</p>
        <p><strong>Snapshot observed:</strong> {observationDate(results.data.meta.observed_at)}</p>
        <p>Showing {results.data.data.length} of {results.data.meta.total} matching snapshot records. {search.latitude === undefined ? 'No origin supplied; distance is unavailable.' : `Ranked from manual origin ${search.latitude}, ${search.longitude}.`}</p>
      </div>
      {results.data.data.length === 0 ? <p className="muted">No matching records in this snapshot. Try another name or address, or enter the branch manually. This does not mean no restaurant exists.</p> : <ul className="discovery-results">
        {results.data.data.map(place => {
          const link = sourceLink(place.source_url);
          return <li key={place.osm_id}>
            <h3>{place.name.trim() || 'Unnamed place'}</h3>
            <p className="discovery-address">{place.address.trim() || 'Address not recorded; verify before saving.'}</p>
            <p className="hint">{place.category.trim() || 'Category unknown'} · {place.latitude.toFixed(6)}, {place.longitude.toFixed(6)}</p>
            <p className="hint">{place.distance_km === null ? 'Distance unavailable' : `${place.distance_km.toLocaleString(undefined, { maximumFractionDigits: 2 })} km straight-line from manual origin; not a route`}</p>
            <div className="discovery-source">
              <p>OpenStreetMap record {place.osm_id}{link && <> · <a href={link} target="_blank" rel="noopener noreferrer">View source</a></>}</p>
              {!link && <p>Source link unavailable.</p>}
              <p>License: {place.license.trim() || 'Unknown'} · Observed: {observationDate(place.observed_at)}</p>
            </div>
            <button type="button" onClick={() => {
              const accepted = onChoose({ osm_id: place.osm_id, name: place.name, address: place.address, latitude: place.latitude, longitude: place.longitude });
              if (accepted) setChosen(place.name.trim() || 'Unnamed place');
            }}>Review this branch</button>
          </li>;
        })}
      </ul>}
    </>}
    <p className="hint">Choosing a result only fills a draft. Review the exact branch, address and pin, then confirm in the save form. Nothing is saved here.</p>
    <p role="status" className="discovery-status">{chosen ? `${chosen} selected for review. Confirm the branch in the save form before saving.` : ''}</p>
  </section>;
}
