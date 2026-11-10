import { useState } from 'react';
import type { FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { createRestaurant, errorMessage, restaurantInputSchema } from './api';
import type { Restaurant } from './api';
import { Discovery } from './Discovery';
import type { PlaceChoice } from './Discovery';
import { PinPicker } from './PinPicker';

interface Props {
  onSaved: (restaurant: Restaurant) => void;
  onCancel: () => void;
  onDirtyChange: (dirty: boolean) => void;
  onSavingChange: (saving: boolean) => void;
}

export function AddRestaurant({ onSaved, onCancel, onDirtyChange, onSavingChange }: Props) {
  const [inputError, setInputError] = useState('');
  const [choice, setChoice] = useState<PlaceChoice | null>(null);
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [draftDirty, setDraftDirty] = useState(false);
  const mutation = useMutation({
    mutationFn: createRestaurant,
    onMutate: () => onSavingChange(true),
    onSuccess: result => onSaved(result.data),
    onSettled: () => onSavingChange(false),
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const parsed = restaurantInputSchema.safeParse({
      name: fields.get('name'), branch: fields.get('branch'), address: fields.get('address'),
      latitude: Number(fields.get('latitude')), longitude: Number(fields.get('longitude')),
      branch_confirmed: fields.get('branch_confirmed') === 'on',
      osm_id: choice?.osm_id,
    });
    if (!parsed.success) {
      setInputError(parsed.error.issues.map(issue => issue.message).join('. '));
      return;
    }
    setInputError('');
    mutation.mutate(parsed.data);
  }

  return <section className="editor" aria-labelledby="add-heading">
    <div className="section-heading"><div><p className="eyebrow">Local discovery or manual entry</p><h2 id="add-heading">Save the right branch</h2></div>
      <button className="quiet" disabled={mutation.isPending} onClick={onCancel}>Cancel</button></div>
    <p className="muted">Use details you know and confirm the coordinates. This form does not fetch Google data or infer a location.</p>
    {!mutation.isPending && <Discovery onChoose={place => {
      if (draftDirty && !window.confirm('Replace this unsaved branch draft with another OSM result?')) return false;
      setChoice(place);
      setLatitude(String(place.latitude));
      setLongitude(String(place.longitude));
      setConfirmed(false);
      onDirtyChange(true);
      setDraftDirty(true);
      return true;
    }} />}
    {choice && <p className="hint">OSM suggestion selected. Correct missing address details and confirm the exact pin before saving.</p>}
    <form key={choice?.osm_id ?? 'manual'} onSubmit={submit} onChange={event => {
      onDirtyChange(true);
      setDraftDirty(true);
      if (!(event.target instanceof HTMLInputElement) || event.target.name !== 'branch_confirmed') setConfirmed(false);
    }}>
      <fieldset disabled={mutation.isPending}>
        <label>Restaurant name<input autoFocus name="name" required maxLength={160} autoComplete="off" defaultValue={choice?.name ?? ''} /></label>
        <label>Branch label <span className="optional">optional</span><input name="branch" maxLength={160} /></label>
        <label>Street address<textarea name="address" required maxLength={500} rows={2} defaultValue={choice?.address ?? ''} /></label>
        <div className="coordinate-fields">
          <label>Latitude<input name="latitude" type="number" min={-90} max={90} step="any" required inputMode="decimal" value={latitude} onChange={event => setLatitude(event.target.value)} /></label>
          <label>Longitude<input name="longitude" type="number" min={-180} max={180} step="any" required inputMode="decimal" value={longitude} onChange={event => setLongitude(event.target.value)} /></label>
        </div>
        <p className="hint">Coordinates use decimal degrees. Check the exact branch, not only its name.</p>
        {!mutation.isPending && <PinPicker latitude={latitude === '' ? null : Number(latitude)} longitude={longitude === '' ? null : Number(longitude)} onChange={(lat, lon) => {
          setLatitude(String(lat)); setLongitude(String(lon)); setConfirmed(false); setDraftDirty(true); onDirtyChange(true);
        }} />}
        <label className="check"><input type="checkbox" name="branch_confirmed" required checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />I confirm this branch, address and coordinates.</label>
        <p className="privacy-note">Stored on this computer. Not sent to cloud AI.</p>
        {(inputError || mutation.error) && <p role="alert" className="error">{inputError || errorMessage(mutation.error)}</p>}
        <button className="primary" type="submit">{mutation.isPending ? 'Saving branch…' : 'Confirm and save branch'}</button>
      </fieldset>
    </form>
  </section>;
}
