import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AddRestaurant } from './AddRestaurant';
import { RestaurantDetail } from './RestaurantDetail';
import { errorMessage, getRestaurant, listRestaurants, statusLabels } from './api';
import type { Restaurant, SearchFilters } from './api';

function LocationMark() {
  return <svg viewBox="0 0 32 36" width="32" height="36" aria-hidden="true"><path d="M16 33S3 21 3 14a13 13 0 0 1 26 0c0 7-13 19-13 19Z" fill="currentColor" /><circle cx="16" cy="14" r="5" fill="white" /></svg>;
}
const initialFilters: SearchFilters = { q: '', status: '', favoriteOnly: false, offset: 0 };

export function App() {
  const client = useQueryClient();
  const [filters, setFilters] = useState(initialFilters);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState('');
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const collection = useQuery({
    queryKey: ['restaurants', filters],
    queryFn: ({ signal }) => listRestaurants(filters, signal),
  });
  const selected = useQuery({
    queryKey: ['restaurant', selectedId],
    queryFn: ({ signal }) => getRestaurant(selectedId!, signal),
    enabled: selectedId !== null,
  });
  function changeFilters(patch: Partial<SearchFilters>) {
    setFilters(current => ({ ...current, ...patch, offset: 0 }));
  }
  function navigate(action: () => void) {
    if (saving) return;
    if (dirty && !window.confirm('Discard unsaved changes in this panel?')) return;
    setDirty(false);
    action();
  }
  function saved(restaurant: Restaurant, created = false) {
    client.setQueryData(['restaurant', restaurant.id], { data: restaurant });
    void client.invalidateQueries({ queryKey: ['restaurants'] });
    setDirty(false);
    setFilters(current => ({ ...current, offset: 0 }));
    if (created) {
      setSelectedId(restaurant.id);
      setAdding(false);
      setFilters(initialFilters);
    }
    setNotice(created ? `${restaurant.name} saved to your collection.` : 'Personal details saved on this computer.');
  }
  const page = collection.data;

  return <>
    <a className="skip-link" href="#main-content">Skip to content</a>
    <header className="topbar"><a className="brand" href="/" aria-label="FoodRoute home" onClick={event => { event.preventDefault(); navigate(() => { setAdding(false); setSelectedId(null); }); }}><LocationMark /><span>FoodRoute</span></a>
      <div className="region"><span className="region-dot" />Ho Chi Minh City<span className="region-mode">Personal collection</span></div>
      <span className="local-label">Local data · no cloud calls</span></header>
    <main id="main-content" className="workspace">
      <div className="workspace-heading"><div><p className="eyebrow">A place for the places you remember</p><h1>My places</h1>
        <p className="muted">Keep the right branch. Save your own impression.</p></div>
        <button className="primary add-button" disabled={saving} onClick={() => navigate(() => { setAdding(true); setNotice(''); })}>+ Add a restaurant</button></div>
      <div role="status" className="notice">{notice}</div>
      <div className="collection-layout">
        <section className="collection" aria-labelledby="collection-heading">
          <div className="section-heading"><h2 id="collection-heading">Your collection</h2><span className="count">{page?.meta.total ?? '—'} places</span></div>
          <div className="filters">
            <label className="search-label">Find a saved place<input type="search" value={filters.q} maxLength={200} onChange={event => changeFilters({ q: event.target.value })} placeholder="Name, branch or address" /></label>
            <div className="filter-row"><label>List<select value={filters.status} onChange={event => changeFilters({ status: event.target.value })}>
              <option value="">All lists</option>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select></label><label className="check"><input type="checkbox" checked={filters.favoriteOnly} onChange={event => changeFilters({ favoriteOnly: event.target.checked })} />Favorites only</label></div>
          </div>
          {collection.isPending && <p className="loading" role="status">Loading your saved places…</p>}
          {collection.isError && <div className="error" role="alert"><p>{errorMessage(collection.error)}</p><button onClick={() => void collection.refetch()}>Retry loading</button></div>}
          {page && page.data.length === 0 && <div className="empty-state"><LocationMark /><h3>{page.meta.total === 0 && !filters.q && !filters.status && !filters.favoriteOnly ? 'Start with a place you know' : 'No matching saved places'}</h3>
            <p>{filters.q || filters.status || filters.favoriteOnly ? 'Change the search or filters. Your other places are still saved.' : 'Add a restaurant and confirm its branch. No sample records are added to your collection.'}</p>
            <button disabled={saving} onClick={() => { if (filters.q || filters.status || filters.favoriteOnly) setFilters(initialFilters); else navigate(() => setAdding(true)); }}>{filters.q || filters.status || filters.favoriteOnly ? 'Clear filters' : 'Add your first restaurant'}</button></div>}
          {page && page.data.length > 0 && <ul className="restaurant-list">{page.data.map(restaurant => <li key={restaurant.id}>
            <button disabled={saving} className={`restaurant-row ${selectedId === restaurant.id ? 'selected' : ''}`} aria-pressed={selectedId === restaurant.id} onClick={() => navigate(() => { setSelectedId(restaurant.id); setAdding(false); setNotice(''); })}>
              <span className="place-initial" aria-hidden="true">{restaurant.name.slice(0, 1)}</span>
              <span className="row-content"><strong>{restaurant.name}</strong>{restaurant.branch && <span>{restaurant.branch}</span>}<span className="row-address">{restaurant.address}</span>
                <span className={`list-status ${restaurant.personal.status}`}>{statusLabels[restaurant.personal.status]}{restaurant.personal.favorite ? ' · Favorite' : ''}</span></span>
              <span className="row-chevron" aria-hidden="true">›</span>
            </button></li>)}</ul>}
          {page && (page.meta.total > page.meta.limit || filters.offset > 0) && <nav className="pagination" aria-label="Collection pages">
            <button disabled={filters.offset === 0} onClick={() => setFilters(current => ({ ...current, offset: Math.max(0, current.offset - page.meta.limit) }))}>Previous</button>
            <span>{filters.offset + 1}–{Math.min(filters.offset + page.meta.limit, page.meta.total)} of {page.meta.total}</span>
            <button disabled={filters.offset + page.meta.limit >= page.meta.total} onClick={() => setFilters(current => ({ ...current, offset: current.offset + page.meta.limit }))}>Next</button>
          </nav>}
          <p className="collection-footer">Only places you save appear here. External ratings are never replaced by personal ratings.</p>
        </section>
        <div className="detail-column">
          {adding ? <AddRestaurant onSaved={restaurant => saved(restaurant, true)} onCancel={() => navigate(() => setAdding(false))} onDirtyChange={setDirty} onSavingChange={setSaving} /> : selectedId ? <>
            {selected.isPending && <p role="status" className="loading">Loading this branch…</p>}
            {selected.isError && <div className="error" role="alert"><p>{errorMessage(selected.error)}</p><button onClick={() => void selected.refetch()}>Reload this branch</button></div>}
            {selected.data && <RestaurantDetail key={selectedId} restaurant={selected.data.data} onSaved={restaurant => saved(restaurant)} onDirtyChange={setDirty} onSavingChange={setSaving} onReload={() => void selected.refetch()} />}
          </> : <section className="welcome-panel"><div className="route-mark" aria-hidden="true"><LocationMark /></div><h2>Your next good meal<br />starts with the right place.</h2>
            <p>Select a saved restaurant to see the branch, provenance and your private notes.</p>
            <div className="honest-state"><h3>Evidence before recommendations</h3><p>Google ratings, routes, menus and live traffic are not connected yet. Missing information is not a zero rating or a travel estimate.</p></div>
          </section>}
        </div>
      </div>
    </main>
    <footer className="app-footer"><span>FoodRoute · Personal use</span><span>Data stays on this computer. Phone access is not configured.</span></footer>
  </>;
}
