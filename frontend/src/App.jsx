import { useCallback, useMemo, useRef, useState } from "react";
import axios from "axios";
import {
  Alert,
  Button,
  Chip,
  Container,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";

const toFormData = (files, lValue, wValue, tValue, returnCsv = false) => {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append("files", file);
  });
  formData.append("l_value", lValue);
  formData.append("w_value", wValue);
  formData.append("t_value", tValue ?? "");
  formData.append("return_csv", String(returnCsv));
  return formData;
};

const toPartsTableFormData = (files, lValue, wValue, tValue) => {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append("files", file);
  });
  formData.append("l_value", lValue ?? "");
  formData.append("w_value", wValue ?? "");
  formData.append("t_value", tValue ?? "");
  return formData;
};

const toLinesCsvFormData = (files) => {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append("files", file);
  });
  return formData;
};

function App() {
  const fileInputRef = useRef(null);

  const [files, setFiles] = useState([]);
  const [results, setResults] = useState([]); // { part_number, file_name }
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const isSearchDisabled = useMemo(() => {
    return files.length === 0;
  }, [files]);

  const isSearchDisabled = useMemo(
    () => files.length === 0 || isLoading,
    [files.length, isLoading]
  );
  const isCsvDisabled = useMemo(
    () => files.length === 0 || isLoading,
    [files.length, isLoading]
  );

  const handlePickFiles = () => fileInputRef.current?.click();

  const handleFileChange = (e) => {
    const selected = Array.from(e.target.files || []);
    if (!selected.length) return;

    setFiles((prev) => {
      const keyOf = (f) => `${f.name}-${f.size}-${f.lastModified}`;
      const exist = new Set(prev.map(keyOf));
      const merged = [...prev];
      for (const f of selected) {
        const k = keyOf(f);
        if (!exist.has(k)) merged.push(f);
      }
      return merged;
    });

    e.target.value = "";
  };

  const executeSearch = useCallback(
    async ({ returnCsv = false, silent = false } = {}) => {
      if (isSearchDisabled) {
        return;
      }

      if (!returnCsv && !silent) {
        setIsLoading(true);
      }
      setError("");

      try {
        if (returnCsv) {
          const response = await axios.post(
            "/api/search",
            toFormData(files, lValue, wValue, tValue, true),
            {
              responseType: "blob",
            }
          );

          const blob = new Blob([response.data], { type: "text/csv" });
          const url = window.URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.setAttribute("download", "search_results.csv");
          document.body.appendChild(link);
          link.click();
          link.remove();
          window.URL.revokeObjectURL(url);
        } else {
          const response = await axios.post(
            "/api/extract_part_numbers_from_table",
            toPartsTableFormData(files, lValue, wValue, tValue)
          );
          const flattened = response.data.flatMap((entry) =>
            entry.part_numbers.map((partNumber) => ({
              file_name: entry.file_name,
              part_number: partNumber,
            }))
          );
          setResults(flattened);
        }
      } catch (err) {
        setError(
          err.response?.data?.detail ||
            (returnCsv ? "CSVダウンロードに失敗しました。" : "検索中にエラーが発生しました。")
        );
      } finally {
        if (!returnCsv && !silent) {
          setIsLoading(false);
        }
      }
    },
    [files, lValue, wValue, tValue, isSearchDisabled]
  );

  const handleRemoveFile = (idx) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  const downloadBlob = (blob, filename) => {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  };

  const handleDownloadPartsListCsv = async () => {
    if (isSearchDisabled) {
      return;
    }

    setIsLoading(true);
    setError("");
    setResults([]);

    try {
      const response = await axios.post(
        "/api/extract_parts_list_csv",
        toPartsTableFormData(files, lValue, wValue, tValue),
        {
          responseType: "blob",
        }
      );

      const blob = new Blob([response.data], { type: "text/csv" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", "parts_list.csv");
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err?.response?.data?.detail || "PART No. 抽出に失敗しました。");
    } finally {
      setIsLoading(false);
    }
  }, [files, lValue, wValue, tValue, isSearchDisabled]);

  // B) parts_list.csv ダウンロード（同じ条件で絞る）
  const handleDownloadPartsListCsv = useCallback(async () => {
    if (isCsvDisabled) return;

    setError("");

    try {
      const form = buildFormData(files, lValue, wValue, tValue);

      const res = await axios.post("/api/extract_parts_list_csv", form, {
        responseType: "blob",
      });

      downloadBlob(new Blob([res.data], { type: "text/csv" }), "parts_list.csv");
    } catch (err) {
      setError(err?.response?.data?.detail || "parts_list.csv の取得に失敗しました。");
    }
  }, [files, lValue, wValue, tValue, isCsvDisabled]);

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Paper elevation={3} sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Typography variant="h5" fontWeight="bold">
            部品番号抽出ツール
          </Typography>

          {error && <Alert severity="error">{error}</Alert>}

          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf"
              multiple
              style={{ display: "none" }}
              onChange={handleFileChange}
            />
            <Button variant="contained" onClick={handlePickFiles} disabled={isLoading}>
              PDFファイルを選択
            </Button>
            <Button variant="outlined" onClick={handleClear} disabled={isLoading}>
              クリア
            </Button>
            <Typography variant="body2">選択中: {files.length} 件</Typography>
          </Stack>

          {files.length > 0 && (
            <Stack direction="row" spacing={1} flexWrap="wrap">
              {files.map((f, idx) => (
                <Chip
                  key={`${f.name}-${f.size}-${f.lastModified}`}
                  label={f.name}
                  onDelete={() => handleRemoveFile(idx)}
                  sx={{ mb: 1 }}
                />
              ))}
            </Stack>
          )}

          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField label="L値" value={lValue} onChange={(e) => setLValue(e.target.value)} fullWidth />
            <TextField label="W値" value={wValue} onChange={(e) => setWValue(e.target.value)} fullWidth />
            <TextField label="T値（厚み）" value={tValue} onChange={(e) => setTValue(e.target.value)} fullWidth />
          </Stack>

          <Stack direction="row" spacing={2} flexWrap="wrap">
            <Button variant="contained" onClick={handleSearch} disabled={isSearchDisabled}>
              {isLoading ? "処理中..." : "検索（PART NO.抽出）"}
            </Button>
            <Button
              variant="outlined"
              startIcon={<DownloadIcon />}
              onClick={handleDownloadPartsListCsv}
              disabled={isSearchDisabled}
            >
              部品一覧CSVダウンロード
            </Button>

            <Button variant="outlined" disabled>
              PDF行CSVダウンロード（未使用）
            </Button>
          </Stack>

          <TableContainer sx={{ mt: 1 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>部品番号</TableCell>
                  <TableCell>ファイル名</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {results.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={2} align="center">
                      検索結果がここに表示されます。
                    </TableCell>
                  </TableRow>
                ) : (
                  results.map((row, index) => (
                    <TableRow key={`${row.file_name}-${index}`}>
                      <TableCell>{row.part_number}</TableCell>
                      <TableCell>{row.file_name}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Stack>
      </Paper>
    </Container>
  );
}

export default App;
