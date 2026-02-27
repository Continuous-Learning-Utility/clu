using UnityEngine;

/// <summary>
/// Simple valid MonoBehaviour for testing.
/// </summary>
public class SampleValid : MonoBehaviour
{
    [SerializeField] private float _speed = 5f;

    private void Update()
    {
        transform.Translate(Vector3.forward * _speed * Time.deltaTime);
    }
}
