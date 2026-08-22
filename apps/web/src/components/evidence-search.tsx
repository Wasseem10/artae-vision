"use client";

import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { Icon } from "@/components/icon";
import { api, evidenceContentUrl } from "@/lib/api";
import type { Camera, EvidenceSearch, EvidenceSearchHit } from "@/lib/types";

interface EvidenceSearchProps {
  camera: Camera | null;
  onError: (message: string) => void;
}

function formatMoment(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${Math.floor(seconds % 60).toString().padStart(2, "0")}`;
}

function SearchPlayer({ hit }: { hit: EvidenceSearchHit }) {
  const videoRef = useRef<HTMLVideoElement>(null);

  return (
    <div className="searchPlayer">
      <video
        controls
        key={`${hit.evidence_id}-${hit.time_start}`}
        onLoadedMetadata={() => {
          if (videoRef.current) videoRef.current.currentTime = hit.time_start;
        }}
        preload="metadata"
        ref={videoRef}
        src={evidenceContentUrl(hit.content_url)}
      />
      <div>
        <span>{hit.camera_name}</span>
        <strong>{hit.summary}</strong>
        <small>
          Match at {formatMoment(hit.time_start)}–{formatMoment(hit.time_end)} ·{" "}
          {Math.round(hit.similarity * 100)}%
        </small>
      </div>
    </div>
  );
}

export function EvidenceSearchPanel({ camera, onError }: EvidenceSearchProps) {
  const [query, setQuery] = useState("");
  const [cameraOnly, setCameraOnly] = useState(false);
  const [search, setSearch] = useState<EvidenceSearch | null>(null);
  const [selectedHit, setSelectedHit] = useState<EvidenceSearchHit | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!search || !["queued", "searching"].includes(search.status)) return;
    const timer = window.setInterval(() => {
      void api
        .getEvidenceSearch(search.id)
        .then((next) => {
          setSearch(next);
          if (next.status === "completed" && next.results[0]) setSelectedHit(next.results[0]);
        })
        .catch((failure: unknown) => {
          onError(failure instanceof Error ? failure.message : "Could not refresh the search.");
        });
    }, 1200);
    return () => window.clearInterval(timer);
  }, [onError, search]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (query.trim().length < 2) return;
    setBusy(true);
    try {
      const next = await api.createEvidenceSearch(
        query.trim(),
        cameraOnly ? (camera?.id ?? null) : null,
      );
      setSearch(next);
      setSelectedHit(next.results[0] ?? null);
    } catch (failure) {
      onError(failure instanceof Error ? failure.message : "Evidence search failed.");
    } finally {
      setBusy(false);
    }
  }

  const waiting = search && ["queued", "searching"].includes(search.status);
  return (
    <section className="panel searchPanel" id="search">
      <div className="panelHeader">
        <div>
          <span className="eyebrow">Natural-language retrieval</span>
          <h2>Search recorded evidence</h2>
        </div>
        {search && (
          <span className={`searchProvider provider-${search.provider}`}>
            {search.provider === "artae_labs" ? "Artae Labs" : "Local metadata"}
          </span>
        )}
      </div>
      <form className="searchForm" onSubmit={submit}>
        <label>
          <span>Describe the moment you want to find</span>
          <div className="searchInputRow">
            <Icon name="search" />
            <input
              onChange={(event) => setQuery(event.target.value)}
              placeholder="A person waiting near the loading door"
              type="search"
              value={query}
            />
            <button
              className="buttonPrimary"
              disabled={busy || query.trim().length < 2}
              type="submit"
            >
              {busy ? "Searching…" : "Search"}
            </button>
          </div>
        </label>
        <label className="cameraScope">
          <input
            checked={cameraOnly}
            disabled={!camera}
            onChange={(event) => setCameraOnly(event.target.checked)}
            type="checkbox"
          />
          Only {camera?.name ?? "the selected camera"}
        </label>
      </form>

      {search?.last_error && <p className="searchNotice">{search.last_error}</p>}
      {waiting ? (
        <div className="searchEmpty">
          <span className="searchPulse" />Index worker is searching video moments…
        </div>
      ) : search && search.results.length === 0 ? (
        <div className="searchEmpty">No recorded evidence matched this description.</div>
      ) : !search ? (
        <div className="searchEmpty">
          Search works locally now and upgrades to timecoded Gemini matches when Artae indexing
          is available.
        </div>
      ) : (
        <div className="searchWorkspace">
          <div className="searchResults" aria-label="Evidence search results">
            {search.results.map((hit) => (
              <button
                className={
                  selectedHit?.evidence_id === hit.evidence_id
                    ? "searchResult selected"
                    : "searchResult"
                }
                key={`${hit.evidence_id}-${hit.time_start}`}
                onClick={() => setSelectedHit(hit)}
                type="button"
              >
                <span>{Math.round(hit.similarity * 100)}%</span>
                <strong>{hit.summary}</strong>
                <small>{hit.camera_name} · {formatMoment(hit.time_start)}</small>
              </button>
            ))}
          </div>
          {selectedHit && <SearchPlayer hit={selectedHit} />}
        </div>
      )}
    </section>
  );
}
