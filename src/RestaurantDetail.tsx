import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { errorMessage, savePersonal, statusLabels } from './api';
import type { PersonalInput, Restaurant } from './api';

interface Props {
  restaurant: Restaurant;
  onSaved: (restaurant: Restaurant) => void;
  onDirtyChange: (dirty: boolean) => void;
  onSavingChange: (saving: boolean) => void;
  onReload: () => void;
}

export function RestaurantDetail({ restaurant, onSaved, onDirtyChange, onSavingChange, onReload }: Props) {
  return <article className="detail" aria-labelledby="detail-heading">
    <div className="section-heading"><p className="eyebrow">Confirmed branch</p><span className="source-tag">Manual source</span></div>
    <h2 id="detail-heading">{restaurant.name}</h2>
    {restaurant.branch && <p className="branch-name">{restaurant.branch}</p>}
    <p className="address">{restaurant.address}</p>
    <dl className="facts">
      <div><dt>Google rating</dt><dd>Not available</dd></div>
      <div><dt>Route / traffic</dt><dd>Not calculated</dd></div>
      <div><dt>Coordinates</dt><dd>{restaurant.latitude.toFixed(6)}, {restaurant.longitude.toFixed(6)}</dd></div>
      <div><dt>Identity version</dt><dd>{restaurant.version}</dd></div>
    </dl>
    <section className="provenance" aria-labelledby="source-heading">
      <h3 id="source-heading">Where this record comes from</h3>
      <p>{restaurant.source.permission_basis}</p>
      <p>Recorded {new Date(restaurant.source.observed_at).toLocaleString()}.</p>
      <p>Private local record. Cloud processing is not permitted.</p>
      {restaurant.source.osm_origin && <div className="osm-evidence">
        <p>Original OSM record: {restaurant.source.osm_origin.osm_id}</p>
        <p>{restaurant.source.osm_origin.name} · {restaurant.source.osm_origin.address || 'Address not recorded'}</p>
        <p>Snapshot {new Date(restaurant.source.osm_origin.observed_at).toLocaleString()} · {restaurant.source.osm_origin.license}</p>
        <p><a href={`https://www.openstreetmap.org/${restaurant.source.osm_origin.osm_id}`} target="_blank" rel="noopener noreferrer">View OpenStreetMap source</a></p>
        <p>The saved identity is your confirmed version; original source evidence remains separate.</p>
      </div>}
    </section>
    <PersonalEditor restaurant={restaurant} onSaved={onSaved} onDirtyChange={onDirtyChange} onSavingChange={onSavingChange} onReload={onReload} />
  </article>;
}

function PersonalEditor({ restaurant, onSaved, onDirtyChange, onSavingChange, onReload }: Props) {
  const [saved, setSaved] = useState(false);
  const saveButton = useRef<HTMLButtonElement>(null);
  const submitted = useRef(false);
  const mutation = useMutation({
    mutationFn: (input: PersonalInput) => savePersonal(restaurant.id, input),
    onMutate: () => onSavingChange(true),
    onSuccess: result => { setSaved(true); onSaved(result.data); },
    onSettled: () => onSavingChange(false),
  });
  useEffect(() => {
    if (submitted.current && !mutation.isPending) {
      saveButton.current?.focus();
      submitted.current = false;
    }
  }, [mutation.isPending]);
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submitted.current = true;
    setSaved(false);
    const values = new FormData(event.currentTarget);
    const rating = String(values.get('personal_rating') ?? '').trim();
    mutation.mutate({
      favorite: values.get('favorite') === 'on',
      status: values.get('status') as PersonalInput['status'],
      personal_rating: rating === '' ? null : Number(rating),
      notes: String(values.get('notes') ?? ''), revision: restaurant.personal.revision,
    });
  }
  return <section className="personal" aria-labelledby="personal-heading">
    <h3 id="personal-heading">Your take</h3>
    <p className="muted">Your rating and notes are separate from Google and other external sources.</p>
    <form onSubmit={submit} onChange={() => { setSaved(false); onDirtyChange(true); }}>
      <fieldset disabled={mutation.isPending}>
        <label className="check"><input name="favorite" type="checkbox" defaultChecked={restaurant.personal.favorite} />Favorite</label>
        <div className="coordinate-fields">
          <label>Your list<select name="status" defaultValue={restaurant.personal.status}>
            {Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select></label>
          <label>Your rating / 5<input name="personal_rating" type="number" min={0} max={5} step={0.1} defaultValue={restaurant.personal.personal_rating ?? ''} /></label>
        </div>
        <label>Private notes<textarea name="notes" rows={4} maxLength={4000} defaultValue={restaurant.personal.notes} /></label>
        {mutation.error && <div className="error" role="alert"><p>{errorMessage(mutation.error)}</p><button type="button" onClick={onReload}>Reload latest revision, keep my draft</button></div>}
        <div className="save-row"><button ref={saveButton} className="primary" type="submit">{mutation.isPending ? 'Saving…' : 'Save personal details'}</button>
          <span className="muted">Revision {restaurant.personal.revision}</span></div>
        <p role="status" className="save-status">{saved ? 'Personal details saved.' : ''}</p>
      </fieldset>
    </form>
  </section>;
}
